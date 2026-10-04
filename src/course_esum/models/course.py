from datetime import datetime, timezone
import uuid
from typing import Optional, List
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

class EvaluationReport(SQLModel, table=True):
    __tablename__ = "evaluation_reports"

    id: str = Field(
        default_factory=lambda: f"rep_{uuid.uuid4().hex[:12]}",
        primary_key=True,
        index=True
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

    content_hash: Optional[str] = Field(default=None, index=True)
    output_language: str = Field(default="English")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
