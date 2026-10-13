from course_esum.services.providers.base import CourseEvaluationProvider, CourseFetchResult, FetchedReport


class MockCourseProvider(CourseEvaluationProvider):
    """Mock provider for unit tests and local development."""

    def fetch_evaluations(self, course_code: str, max_reports: int = 3) -> CourseFetchResult:
        clean_code = course_code.strip().upper()

        sample_text = f"""
Final report HT2024_{clean_code}_Mock_Course
First time registered students: 15
Answer Count: 10

--- Statistical Results ---
Supportive Structure       3.8 / 5.0
Varied Teaching            3.5 / 5.0
Discussed the Subject      4.0 / 5.0
Challenging                3.5 / 5.0
Feedback Helped            3.0 / 5.0
Workload                   2.5 / 5.0  (too high)

--- Student Free-Text Survey Responses ---

Q: What did you appreciate most about this course?
Student answer: "The lab sessions were genuinely the best part. We got to apply theory straight away and the TAs were always there to help. I felt like I actually learned something each week."
Student answer: "I loved how the lectures connected directly to real industry problems. It made studying feel relevant rather than just abstract theory."
Student answer: "The group project was challenging but rewarding. Working with classmates on a real dataset gave me confidence I didn't have before."

Q: What could be improved?
Student answer: "The exam came out of nowhere — the practice questions didn't really match the actual difficulty. More alignment there would help a lot."
Student answer: "Workload was brutal in weeks 4 and 5. Three deadlines at the same time felt unmanageable and I basically stopped sleeping."
Student answer: "The feedback on assignments was pretty vague. I submitted my second lab and got 'good effort' with no indication of what to fix."

Q: Would you recommend this course?
Student answer: "Yes, definitely — but only if you are ready for a serious time commitment. Don't take it alongside two other heavy courses."

--- Kursledarens reflektion ---
The course ran well overall and the statistical scores confirm a solid foundation. The drop in workload satisfaction was expected given that we introduced a new compulsory group project this term. Going forward, I plan to stagger the deadlines across weeks 4–6 more evenly. The feedback quality issue is noted — I will provide more detailed rubrics for lab submissions in the next iteration. Student engagement in lectures was high, which reflects the new case-study format introduced this term.
        """

        reports = [
            FetchedReport(
                label=f"HT-24 ({clean_code}-MOCK)",
                url=f"https://mock.university.se/evaluations/{clean_code}_2024.pdf",
                pdf_bytes=b"%PDF-1.4 mock pdf content",
                extracted_text=sample_text,
            )
        ]

        return CourseFetchResult(
            course_code=clean_code,
            course_title=f"Mock Course for {clean_code}",
            reports=reports,
        )
