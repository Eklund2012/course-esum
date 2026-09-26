"""University course evaluation provider implementations."""
from course_esum.services.providers.base import (
    CourseEvaluationProvider,
    CourseFetchResult,
    FetchedReport,
)
from course_esum.services.providers.kau_provider import KarlstadUniversityProvider
from course_esum.services.providers.mock_provider import MockCourseProvider

__all__ = [
    "CourseEvaluationProvider",
    "CourseFetchResult",
    "FetchedReport",
    "KarlstadUniversityProvider",
    "MockCourseProvider",
]
