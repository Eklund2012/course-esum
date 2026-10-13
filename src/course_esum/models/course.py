from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, Text

from course_esum.schemas.evaluation import StudentQuote

__all__ = ["EvaluationReport", "StudentQuote"]


class EvaluationReport(SQLModel, table=True):
    __tablename__ = "evaluation_reports"

    id: str = Field(
        default_factory=lambda: f"rep_{uuid.uuid4().hex[:12]}",
        primary_key=True,
        index=True,
    )
    job_id: str = Field(index=True, foreign_key="evaluation_jobs.id")
    course_code: Optional[str] = Field(default=None, index=True)
    course_name_and_code: str

    # Store list of strings as JSON in DB
    positive_summary: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    critique_summary: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    workload: str
    trend_over_time: str
    reports_analyzed: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Cohort metrics (nullable — may not be present in all reports)
    respondents_count: Optional[int] = Field(default=None)
    registered_count: Optional[int] = Field(default=None)
    response_rate_percent: Optional[float] = Field(default=None)

    # Structured student quotes — list of {quote, sentiment, context} dicts stored as JSON.
    # Each dict maps 1-to-1 with the StudentQuote Pydantic model.
    student_quotes: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    # Teacher/coordinator reflection, kept strictly separate from student survey data.
    teacher_reflection: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    content_hash: Optional[str] = Field(default=None, index=True)
    output_language: str = Field(default="English")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
