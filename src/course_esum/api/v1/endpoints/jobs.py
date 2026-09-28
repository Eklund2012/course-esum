import json
import asyncio
from fastapi import APIRouter, HTTPException, Depends, status
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session, select
from course_esum.api.dependencies import DbDep, AuthDep, AuthQueryDep
from course_esum.models.job import EvaluationJob
from course_esum.models.course import EvaluationReport
from course_esum.schemas.job import JobResponse, JobStatus, InputType
from course_esum.schemas.evaluation import EvaluationReportResponse
from course_esum.services.job_runner import subscribe_to_job, unsubscribe_from_job

router = APIRouter(tags=["Jobs"])

@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get background job status & result",
    dependencies=[AuthDep]
)
def get_job_status(job_id: str, session: Session = DbDep):
    """Poll the status and final results of an evaluation job."""
    job = session.exec(select(EvaluationJob).where(EvaluationJob.id == job_id)).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' does not exist."
        )

    # If completed, attach report result
    result_data = None
    if job.status == JobStatus.COMPLETED.value:
        report = session.exec(select(EvaluationReport).where(EvaluationReport.job_id == job.id)).first()
        if report:
            result_data = EvaluationReportResponse(
                course_name_and_code=report.course_name_and_code,
                positive_summary=report.positive_summary or [],
                critique_summary=report.critique_summary or [],
                workload=report.workload,
                trend_over_time=report.trend_over_time,
                reports_analyzed=report.reports_analyzed or [],
                output_language=report.output_language,
                cached=bool(report.content_hash)
            )

    return JobResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        input_type=InputType(job.input_type),
        course_code=job.course_code,
        output_language=job.output_language,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        result=result_data
    )

@router.get(
    "/jobs/{job_id}/stream",
    summary="Subscribe to real-time Server-Sent Events (SSE) for a job",
    dependencies=[AuthQueryDep]
)
async def stream_job_events(job_id: str, session: Session = DbDep):
    """
    Real-time SSE event stream.
    Emits events as the job transitions through PENDING -> PROCESSING -> COMPLETED/FAILED.
    """
    job = session.exec(select(EvaluationJob).where(EvaluationJob.id == job_id)).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' does not exist."
        )

    async def event_generator():
        queue = subscribe_to_job(job_id)
        try:
            # Send initial current status
            yield {
                "event": "status",
                "data": json.dumps({"job_id": job.id, "status": job.status})
            }

            # If already completed or failed, close stream
            if job.status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                return

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "update",
                        "data": json.dumps(event_data)
                    }
                    if event_data.get("status") in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": "keep-alive"})
                    }
        finally:
            unsubscribe_from_job(job_id, queue)

    return EventSourceResponse(event_generator())
