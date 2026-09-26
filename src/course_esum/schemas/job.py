from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from course_esum.schemas.evaluation import EvaluationReportResponse

class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class InputType(str, Enum):
    FILE_UPLOAD = "FILE_UPLOAD"
    COURSE_CODE = "COURSE_CODE"

class JobCreatedResponse(BaseModel):
    """Returned on 202 Accepted when a background job is enqueued."""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    input_type: InputType
    course_code: Optional[str] = None
    created_at: datetime
    links: Dict[str, str]

class JobResponse(BaseModel):
    """Full status and result payload for a job."""
    job_id: str
    status: JobStatus
    input_type: InputType
    course_code: Optional[str] = None
    output_language: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[EvaluationReportResponse] = None
