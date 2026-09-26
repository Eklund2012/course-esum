import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from sqlmodel import Session, select
from course_esum.core.database import engine
from course_esum.models.job import EvaluationJob
from course_esum.models.course import EvaluationReport
from course_esum.schemas.job import JobStatus, InputType
from course_esum.services.summarizer import SummarizerService
from course_esum.services.providers.kau_provider import KarlstadUniversityProvider

# In-memory pub/sub queues for Server-Sent Events (SSE)
_job_listeners: Dict[str, List[asyncio.Queue]] = {}

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
        with Session(engine) as session:
            job = session.exec(select(EvaluationJob).where(EvaluationJob.id == job_id)).first()
            if not job:
                return

            try:
                # 1. Transition to PROCESSING
                job.status = JobStatus.PROCESSING.value
                session.add(job)
                session.commit()
                await broadcast_job_event(job_id, {"status": JobStatus.PROCESSING.value, "message": f"Fetching evaluations for {course_code}..."})

                # 2. Fetch reports via Provider
                provider = KarlstadUniversityProvider()
                fetch_result = provider.fetch_evaluations(course_code, max_reports=max_reports)
                
                await broadcast_job_event(job_id, {
                    "status": JobStatus.PROCESSING.value,
                    "message": f"Analyzing {len(fetch_result.reports)} report(s) with Gemini AI...",
                    "course_title": fetch_result.course_title
                })

                # 3. Summarize using Gemini Multimodal PDF Engine
                summarizer = SummarizerService()
                summary = summarizer.summarize_from_pdf_documents(
                    fetch_result.documents,
                    output_language=output_language
                )

                # 4. Persist EvaluationReport
                report = EvaluationReport(
                    job_id=job.id,
                    course_code=course_code.upper(),
                    course_name_and_code=summary.course_name_and_code,
                    positive_summary=summary.positive_summary,
                    critique_summary=summary.critique_summary,
                    workload=summary.workload,
                    trend_over_time=summary.trend_over_time,
                    reports_analyzed=[r.label for r in fetch_result.reports],
                    output_language=output_language
                )
                session.add(report)

                # 5. Mark Job as COMPLETED
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()

                await broadcast_job_event(job_id, {
                    "status": JobStatus.COMPLETED.value,
                    "message": "Evaluation summary completed successfully.",
                    "data": summary.model_dump()
                })

            except Exception as exc:
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()

                await broadcast_job_event(job_id, {
                    "status": JobStatus.FAILED.value,
                    "error": str(exc)
                })

    @classmethod
    async def run_file_upload_job(
        cls,
        job_id: str,
        documents: List[Tuple[str, bytes]],
        output_language: str = "English"
    ) -> None:
        """Processes uploaded PDF documents in the background."""
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
                    "message": f"Analyzing {len(documents)} uploaded PDF document(s) with Gemini AI..."
                })

                # 2. Summarize
                summarizer = SummarizerService()
                summary = summarizer.summarize_from_pdf_documents(
                    documents,
                    output_language=output_language
                )

                # 3. Persist Report
                report = EvaluationReport(
                    job_id=job.id,
                    course_name_and_code=summary.course_name_and_code,
                    positive_summary=summary.positive_summary,
                    critique_summary=summary.critique_summary,
                    workload=summary.workload,
                    trend_over_time=summary.trend_over_time,
                    reports_analyzed=[label for label, _ in documents],
                    output_language=output_language
                )
                session.add(report)

                # 4. Mark Job as COMPLETED
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()

                await broadcast_job_event(job_id, {
                    "status": JobStatus.COMPLETED.value,
                    "message": "Evaluation summary completed successfully.",
                    "data": summary.model_dump()
                })

            except Exception as exc:
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()

                await broadcast_job_event(job_id, {
                    "status": JobStatus.FAILED.value,
                    "error": str(exc)
                })
