from course_esum.services.providers.base import CourseEvaluationProvider, CourseFetchResult, FetchedReport

class MockCourseProvider(CourseEvaluationProvider):
    """Mock provider for unit tests and local development."""

    def fetch_evaluations(self, course_code: str, max_reports: int = 3) -> CourseFetchResult:
        clean_code = course_code.strip().upper()
        
        sample_text = f"""
Final report HT2024_{clean_code}_Mock_Course
First time registered students: 15
Answer Count: 10
Supportive Structure 3.8
Varied Teaching 3.5
Discussed the Subject 4.0
Challenging 3.5
Feedback Helped 3.0
Workload 2.5
Results of learning: Students found the mock course engaging and practical.
        """

        reports = [
            FetchedReport(
                label=f"HT-24 ({clean_code}-MOCK)",
                url=f"https://mock.university.se/evaluations/{clean_code}_2024.pdf",
                pdf_bytes=b"%PDF-1.4 mock pdf content",
                extracted_text=sample_text
            )
        ]

        return CourseFetchResult(
            course_code=clean_code,
            course_title=f"Mock Course for {clean_code}",
            reports=reports
        )
