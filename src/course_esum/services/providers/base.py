from abc import ABC, abstractmethod
from typing import List, Tuple
from pydantic import BaseModel

class FetchedReport(BaseModel):
    label: str
    url: str
    pdf_bytes: bytes
    extracted_text: str = ""

class CourseFetchResult(BaseModel):
    course_code: str
    course_title: str
    reports: List[FetchedReport]
    
    @property
    def documents(self) -> List[Tuple[str, bytes]]:
        return [(r.label, r.pdf_bytes) for r in self.reports]

class CourseEvaluationProvider(ABC):
    """Abstract interface for university course evaluation providers."""
    
    @abstractmethod
    def fetch_evaluations(self, course_code: str, max_reports: int = 3) -> CourseFetchResult:
        """Fetches official evaluation reports for the given course code."""
        pass
