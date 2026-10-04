import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

from sqlmodel import Session, select

from course_esum.config import get_settings
from course_esum.core.database import engine
from course_esum.models.job import EvaluationJob
from course_esum.models.course import EvaluationReport
from course_esum.schemas.job import JobStatus, InputType
from course_esum.services.summarizer import SummarizerService
from course_esum.services.providers.kau_provider import KarlstadUniversityProvider

logger = logging.getLogger(__name__)

# In-memory pub/sub queues for Server-Sent Events (SSE)
_job_listeners: Dict[str, List[asyncio.Queue]] = {}

# Shared thread pool for offloading blocking Gemini calls without blocking the
# event loop. A bounded pool prevents runaway parallelism in production.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini-worker")


def subscribe_to_job(job_id: str) -> asyncio.Queue:
    """Subscribe an SSE listener to real-time events for a job."""
    queue: asyncio.Queue = asyncio.Queue()
    if job_id not in _job_listeners:
        _job_listeners[job_id] = []
    _job_listeners[job_id].append(queue)
    return queue


def unsubscribe_from_job(job_id: str, queue: asyncio.Queue) -> None:
    """Remove an SSE listener."""
    if job_id in _job_listeners:
        _job_listeners[job_id] = [q for q in _job_listeners[job_id] if q is not queue]
        if not _job_listeners[job_id]:
            del _job_listeners[job_id]


async def broadcast_job_event(job_id: str, event_data: dict) -> None:
    """Broadcast an event to all active SSE subscribers of a job."""
    if job_id in _job_listeners:
        for queue in _job_listeners[job_id]:
            await queue.put(event_data)


def _sanitize_error(exc: BaseException) -> str:
    """
    Convert an exception into a short, user-readable message.

    Raw Python tracebacks and internal error strings are logged at WARNING
    level for debugging but are never exposed directly to API callers.
    """
    logger.warning("Job error: %s: %s", type(exc).__name__, exc, exc_info=True)

    # Exceptions we raise explicitly already have user-facing messages.
    if isinstance(exc, (ValueError, RuntimeError)):
        msg = str(exc)
        # Truncate very long messages defensively
        return msg[:300] if len(msg) <= 300 else msg[:297] + "…"

    if isinstance(exc, asyncio.TimeoutError):
        return "The AI summarization step timed out. Please try again in a moment."

    # Fall back to a generic message for unexpected failures
    return "An unexpected error occurred during processing. Please try again."


class JobRunner:
    """Orchestrates background execution, state transitions, and AI summarization."""

    @classmethod
    async def run_course_code_job(
        cls,
        job_id: str,
        course_code: str,
        output_language: str = "English",
        max_reports: int = 3
    ) -> None:
        """Processes a course-code lookup job in the background."""
        settings = get_settings()

        with Session(engine) as session:
            job = session.exec(select(EvaluationJob).where(EvaluationJob.id == job_id)).first()
            if not job:
                return

            try:
                # 1. Transition to PROCESSING
                job.status = JobStatus.PROCESSING.value
                session.add(job)
                session.commit()
                await broadcast_job_event(
                    job_id,
                    {"status": JobStatus.PROCESSING.value, "message": f"Fetching evaluations for {course_code}…"}
                )

                # 2. Fetch reports via Provider (network I/O — run in executor)
                loop = asyncio.get_event_loop()
                provider = KarlstadUniversityProvider()
                fetch_result = await loop.run_in_executor(
                    _executor,
                    lambda: provider.fetch_evaluations(course_code, max_reports=max_reports)
                )

                await broadcast_job_event(job_id, {
                    "status": JobStatus.PROCESSING.value,
                    "message": f"Analyzing {len(fetch_result.reports)} report(s) with Gemini AI…",
                    "course_title": fetch_result.course_title
                })

                # 3. Summarize using Gemini — enforces GEMINI_TIMEOUT_SECS wall-clock limit
                summarizer = SummarizerService()
                summary = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda: summarizer.summarize_from_pdf_documents(
                            fetch_result.documents,
                            output_language=output_language
                        )
                    ),
                    timeout=settings.GEMINI_TIMEOUT_SECS,
                )

                # 4. Persist EvaluationReport and mark Job COMPLETED atomically
                report = EvaluationReport(
                    job_id=job.id,
                    course_code=course_code.upper(),
                    course_name_and_code=summary.course_name_and_code,
                    positive_summary=summary.positive_summary,
                    critique_summary=summary.critique_summary,
                    workload=summary.workload,
                    trend_over_time=summary.trend_over_time,
                    reports_analyzed=[r.label for r in fetch_result.reports],
                    output_language=output_language,
                    respondents_count=summary.respondents_count,
                    registered_count=summary.registered_count,
                    response_rate_percent=summary.response_rate_percent,
                )
                session.add(report)

                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()  # single commit — report + job state are atomic

                await broadcast_job_event(job_id, {
                    "status": JobStatus.COMPLETED.value,
                    "message": "Evaluation summary ready.",
                    "data": summary.model_dump()
                })

            except Exception as exc:
                user_message = _sanitize_error(exc)
                try:
                    job.status = JobStatus.FAILED.value
                    job.error_message = user_message
                    job.completed_at = datetime.now(timezone.utc)
                    session.add(job)
                    session.commit()
                except Exception:
                    logger.exception("Failed to persist FAILED status for job %s", job_id)

                await broadcast_job_event(job_id, {
                    "status": JobStatus.FAILED.value,
                    "error": user_message
                })

    @classmethod
    async def run_file_upload_job(
        cls,
        job_id: str,
        documents: List[Tuple[str, bytes]],
        output_language: str = "English"
    ) -> None:
        """Processes uploaded PDF documents in the background."""
        settings = get_settings()

        with Session(engine) as session:
            job = session.exec(select(EvaluationJob).where(EvaluationJob.id == job_id)).first()
            if not job:
                return

            try:
                # 1. Transition to PROCESSING
                job.status = JobStatus.PROCESSING.value
                session.add(job)
                session.commit()
                await broadcast_job_event(job_id, {
                    "status": JobStatus.PROCESSING.value,
                    "message": f"Analyzing {len(documents)} uploaded PDF document(s) with Gemini AI…"
                })

                # 2. Summarize — enforces GEMINI_TIMEOUT_SECS wall-clock limit
                loop = asyncio.get_event_loop()
                summarizer = SummarizerService()
                summary = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda: summarizer.summarize_from_pdf_documents(
                            documents,
                            output_language=output_language
                        )
                    ),
                    timeout=settings.GEMINI_TIMEOUT_SECS,
                )

                # 3. Persist Report and mark Job COMPLETED atomically
                report = EvaluationReport(
                    job_id=job.id,
                    course_name_and_code=summary.course_name_and_code,
                    positive_summary=summary.positive_summary,
                    critique_summary=summary.critique_summary,
                    workload=summary.workload,
                    trend_over_time=summary.trend_over_time,
                    reports_analyzed=[label for label, _ in documents],
                    output_language=output_language,
                    respondents_count=summary.respondents_count,
                    registered_count=summary.registered_count,
                    response_rate_percent=summary.response_rate_percent,
                )
                session.add(report)

                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()  # single commit — report + job state are atomic

                await broadcast_job_event(job_id, {
                    "status": JobStatus.COMPLETED.value,
                    "message": "Evaluation summary ready.",
                    "data": summary.model_dump()
                })

            except Exception as exc:
                user_message = _sanitize_error(exc)
                try:
                    job.status = JobStatus.FAILED.value
                    job.error_message = user_message
                    job.completed_at = datetime.now(timezone.utc)
                    session.add(job)
                    session.commit()
                except Exception:
                    logger.exception("Failed to persist FAILED status for job %s", job_id)

                await broadcast_job_event(job_id, {
                    "status": JobStatus.FAILED.value,
                    "error": user_message
                })
