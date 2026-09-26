from datetime import datetime, timezone
import uuid
from typing import Optional
from sqlmodel import SQLModel, Field
from course_esum.schemas.job import JobStatus, InputType

class EvaluationJob(SQLModel, table=True):
    __tablename__ = "evaluation_jobs"

    id: str = Field(
        default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}",
        primary_key=True,
        index=True
    )
    status: str = Field(default=JobStatus.PENDING.value, index=True)
    input_type: str = Field(default=InputType.COURSE_CODE.value)
    course_code: Optional[str] = Field(default=None, index=True)
    output_language: str = Field(default="English")
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
