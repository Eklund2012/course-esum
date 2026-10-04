from typing import List, Optional
from pydantic import BaseModel, Field

class CourseEvaluationSummary(BaseModel):
    """Structured Pydantic model for Gemini AI evaluation extraction."""
    course_name_and_code: str = Field(
        description="The formal name of the course and its course code (e.g. 'Aktuell forskning inom datanätverk (DVAE24)')"
    )
    positive_summary: List[str] = Field(
        default_factory=list,
        description="Concise bullet points summarizing positive feedback and high-scoring aspects"
    )
    critique_summary: List[str] = Field(
        default_factory=list,
        description="Concise bullet points summarizing critique, pain points, or areas for improvement"
    )
    workload: str = Field(
        description="Assessment of student workload (e.g. 'appropriate', 'too high', 'too low', or 'no information')"
    )
    trend_over_time: str = Field(
        description="Analysis of how evaluations have evolved across terms or years if historical data exists"
    )
    respondents_count: Optional[int] = Field(
        default=None,
        description="Total number of students who submitted a response across all analyzed reports. Null if not found."
    )
    registered_count: Optional[int] = Field(
        default=None,
        description="Total number of students registered on the course across all analyzed reports. Null if not found."
    )
    response_rate_percent: Optional[float] = Field(
        default=None,
        description="Response rate as a percentage (respondents / registered * 100), rounded to one decimal. Null if counts are unavailable."
    )

class FetchEvaluationRequest(BaseModel):
    """Payload to trigger automated evaluation fetch by course code."""
    course_code: str = Field(..., min_length=2, max_length=20, examples=["DVAE24", "DVAE23", "ISGB11"])
    output_language: str = Field(default="English", examples=["English", "Swedish"])
    max_reports: int = Field(default=3, ge=1, le=10, description="Max number of past term reports to analyze")

class EvaluationReportResponse(BaseModel):
    """Full API representation of an evaluation report."""
    course_name_and_code: str
    positive_summary: List[str]
    critique_summary: List[str]
    workload: str
    trend_over_time: str
    reports_analyzed: Optional[List[str]] = None
    output_language: str = "English"
    cached: bool = False
    respondents_count: Optional[int] = None
    registered_count: Optional[int] = None
    response_rate_percent: Optional[float] = None
