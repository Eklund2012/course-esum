import io
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException, status
from sqlmodel import Session, select, desc
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from course_esum.api.dependencies import DbDep, AuthDep
from course_esum.config import get_settings
from course_esum.models.job import EvaluationJob
from course_esum.models.course import EvaluationReport
from course_esum.schemas.job import JobCreatedResponse, JobStatus, InputType
from course_esum.schemas.evaluation import FetchEvaluationRequest, EvaluationReportResponse
from course_esum.services.job_runner import JobRunner

router = APIRouter(tags=["Evaluations"])

@router.post(
    "/jobs/fetch",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue course evaluation job by course code",
    dependencies=[AuthDep]
)
def create_fetch_job(
    request: FetchEvaluationRequest,
    background_tasks: BackgroundTasks,
    session: Session = DbDep
):
    """
    Submits an asynchronous job to fetch and summarize evaluations for a university course code (e.g. 'DVAE24').
    Returns 202 Accepted immediately with job tracking links.
    """
    code = request.course_code.strip().upper()
    job = EvaluationJob(
        status=JobStatus.PENDING.value,
        input_type=InputType.COURSE_CODE.value,
        course_code=code,
        output_language=request.output_language
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Schedule background execution
    background_tasks.add_task(
        JobRunner.run_course_code_job,
        job_id=job.id,
        course_code=code,
        output_language=request.output_language,
        max_reports=request.max_reports
    )

    return JobCreatedResponse(
        job_id=job.id,
        status=JobStatus.PENDING,
        input_type=InputType.COURSE_CODE,
        course_code=code,
        created_at=job.created_at,
        links={
            "status": f"/api/v1/evaluations/jobs/{job.id}",
            "stream": f"/api/v1/evaluations/jobs/{job.id}/stream"
        }
    )

@router.post(
    "/jobs/upload",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue course evaluation job by uploading PDF file(s)",
    dependencies=[AuthDep]
)
async def create_upload_job(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="One or more evaluation PDF files"),
    output_language: str = Form(default="English"),
    session: Session = DbDep
):
    """
    Submits an asynchronous job to analyze uploaded evaluation PDF documents.
    Returns 202 Accepted immediately with job tracking links.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one PDF file must be uploaded."
        )

    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Validate each file: MIME type, magic bytes, size, and readability
    documents = []
    for file in files:
        # 1. Content-type header check
        if file.content_type not in ("application/pdf", "application/x-pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"'{file.filename}' has an unsupported type '{file.content_type}'. "
                    "Only PDF files are accepted."
                )
            )

        data = await file.read()

        # 2. Empty file check
        if len(data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{file.filename}' is empty."
            )

        # 3. Size limit check
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"'{file.filename}' is {len(data) // (1024*1024)} MB, which exceeds "
                    f"the {settings.MAX_UPLOAD_SIZE_MB} MB per-file limit."
                )
            )

        # 4. PDF magic-byte check (catches renamed non-PDF files)
        if not data.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{file.filename}' does not appear to be a valid PDF file."
            )

        # 5. Structural validity + password protection check
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"'{file.filename}' is password-protected and cannot be processed. "
                        "Please remove the password and re-upload."
                    )
                )
        except HTTPException:
            raise
        except PdfReadError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{file.filename}' appears to be corrupted or is not a readable PDF."
            )

        documents.append((file.filename, data))

    job = EvaluationJob(
        status=JobStatus.PENDING.value,
        input_type=InputType.FILE_UPLOAD.value,
        output_language=output_language
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Schedule background execution
    background_tasks.add_task(
        JobRunner.run_file_upload_job,
        job_id=job.id,
        documents=documents,
        output_language=output_language
    )

    return JobCreatedResponse(
        job_id=job.id,
        status=JobStatus.PENDING,
        input_type=InputType.FILE_UPLOAD,
        created_at=job.created_at,
        links={
            "status": f"/api/v1/evaluations/jobs/{job.id}",
            "stream": f"/api/v1/evaluations/jobs/{job.id}/stream"
        }
    )

@router.get(
    "/history",
    response_model=List[EvaluationReportResponse],
    summary="Get history of generated course evaluations",
    dependencies=[AuthDep]
)
def get_evaluation_history(
    course_code: Optional[str] = None,
    limit: int = 20,
    session: Session = DbDep
):
    """Retrieve previously generated course evaluation summaries."""
    query = select(EvaluationReport).order_by(desc(EvaluationReport.created_at)).limit(limit)
    if course_code:
        query = query.where(EvaluationReport.course_code == course_code.strip().upper())
        
    reports = session.exec(query).all()
    return [
        EvaluationReportResponse(
            course_name_and_code=r.course_name_and_code,
            positive_summary=r.positive_summary or [],
            critique_summary=r.critique_summary or [],
            workload=r.workload,
            trend_over_time=r.trend_over_time,
            reports_analyzed=r.reports_analyzed or [],
            output_language=r.output_language,
            cached=False
        )
        for r in reports
    ]
