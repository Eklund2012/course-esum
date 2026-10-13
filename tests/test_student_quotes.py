"""
Unit tests for the StudentQuote schema and related backward-compatibility guarantees.

Coverage areas:
- StudentQuote field validation (valid sentiments, optional context)
- Rejection of invalid sentiment literals
- CourseEvaluationSummary defaults — old reports that lack student_quotes or
  teacher_reflection must still deserialize cleanly (backward compat)
- EvaluationReportResponse serializes student_quotes with correct structure
- EvaluationReport DB model stores and re-hydrates student_quotes as dicts
"""
import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool

from course_esum.schemas.evaluation import (
    CourseEvaluationSummary,
    EvaluationReportResponse,
    StudentQuote,
)
from course_esum.models.course import EvaluationReport


# ---------------------------------------------------------------------------
# StudentQuote validation
# ---------------------------------------------------------------------------

class TestStudentQuote:
    def test_valid_positive_quote(self):
        q = StudentQuote(quote="The labs were excellent.", sentiment="positive", context="Lab sessions")
        assert q.quote == "The labs were excellent."
        assert q.sentiment == "positive"
        assert q.context == "Lab sessions"

    def test_valid_critique_quote_no_context(self):
        q = StudentQuote(quote="Pacing was too fast.", sentiment="critique")
        assert q.sentiment == "critique"
        assert q.context is None

    def test_valid_neutral_quote(self):
        q = StudentQuote(quote="The course covered standard topics.", sentiment="neutral", context="Syllabus")
        assert q.sentiment == "neutral"

    def test_invalid_sentiment_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            StudentQuote(quote="Something.", sentiment="negative")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("sentiment",) for e in errors)

    def test_empty_quote_raises(self):
        """Empty string quotes should still pass schema validation (min_length not enforced),
        but the field is required — omitting it must raise."""
        with pytest.raises(ValidationError):
            StudentQuote(sentiment="positive")  # type: ignore[call-arg]

    def test_model_dump_round_trip(self):
        q = StudentQuote(quote="Great lecturer.", sentiment="positive", context="Teaching style")
        dumped = q.model_dump()
        restored = StudentQuote.model_validate(dumped)
        assert restored == q


# ---------------------------------------------------------------------------
# CourseEvaluationSummary — backward compatibility
# ---------------------------------------------------------------------------

class TestCourseEvaluationSummaryDefaults:
    """Old serialized summaries without student_quotes / teacher_reflection must still parse."""

    _LEGACY_PAYLOAD = {
        "course_name_and_code": "Old Course (OLD99)",
        "positive_summary": ["Good lecture quality"],
        "critique_summary": ["Heavy workload"],
        "workload": "too high",
        "trend_over_time": "Stable over 3 terms",
    }

    def test_legacy_payload_parses_without_new_fields(self):
        summary = CourseEvaluationSummary.model_validate(self._LEGACY_PAYLOAD)
        assert summary.student_quotes == []
        assert summary.teacher_reflection is None

    def test_legacy_payload_respondent_counts_default_to_none(self):
        summary = CourseEvaluationSummary.model_validate(self._LEGACY_PAYLOAD)
        assert summary.respondents_count is None
        assert summary.registered_count is None
        assert summary.response_rate_percent is None

    def test_full_payload_with_quotes(self):
        payload = dict(self._LEGACY_PAYLOAD)
        payload["student_quotes"] = [
            {"quote": "Really enjoyed the project work.", "sentiment": "positive", "context": "Projects"},
            {"quote": "The deadlines were very tight.", "sentiment": "critique", "context": None},
        ]
        payload["teacher_reflection"] = "Students generally performed well."
        summary = CourseEvaluationSummary.model_validate(payload)
        assert len(summary.student_quotes) == 2
        assert summary.student_quotes[0].sentiment == "positive"
        assert summary.student_quotes[1].context is None
        assert "performed well" in summary.teacher_reflection


# ---------------------------------------------------------------------------
# EvaluationReportResponse serialization
# ---------------------------------------------------------------------------

class TestEvaluationReportResponse:
    def test_student_quotes_serialized_in_response(self):
        quotes = [
            StudentQuote(quote="Engaging course.", sentiment="positive", context="Overall"),
        ]
        resp = EvaluationReportResponse(
            course_name_and_code="X (X1)",
            positive_summary=["Good"],
            critique_summary=[],
            workload="appropriate",
            trend_over_time="Stable",
            student_quotes=quotes,
            teacher_reflection="Coordinator is happy with results.",
        )
        dumped = resp.model_dump()
        assert len(dumped["student_quotes"]) == 1
        assert dumped["student_quotes"][0]["sentiment"] == "positive"
        assert dumped["teacher_reflection"] == "Coordinator is happy with results."

    def test_response_defaults_empty_quotes_when_omitted(self):
        resp = EvaluationReportResponse(
            course_name_and_code="Y (Y2)",
            positive_summary=[],
            critique_summary=[],
            workload="appropriate",
            trend_over_time="N/A",
        )
        assert resp.student_quotes == []
        assert resp.teacher_reflection is None


# ---------------------------------------------------------------------------
# EvaluationReport DB model — JSON round-trip via in-memory SQLite
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestEvaluationReportPersistence:
    def _make_report(self, job_id: str, quotes: list, reflection: str | None) -> EvaluationReport:
        return EvaluationReport(
            job_id=job_id,
            course_name_and_code="Persistence Test (PT01)",
            positive_summary=["Good"],
            critique_summary=["Bad"],
            workload="appropriate",
            trend_over_time="Stable",
            reports_analyzed=["HT2023"],
            student_quotes=quotes,
            teacher_reflection=reflection,
        )

    def test_student_quotes_stored_and_retrieved(self, db_session: Session):
        # Manufacture a fake foreign-key row so FK constraint is satisfied.
        # For the in-memory DB created from SQLModel metadata the FK is not
        # enforced by SQLite by default, so we can insert the report directly.
        raw_quotes = [
            {"quote": "Loved the lab work.", "sentiment": "positive", "context": "Labs"},
            {"quote": "Exam was too hard.", "sentiment": "critique", "context": "Exam"},
        ]
        report = self._make_report("job_abc123", raw_quotes, "Teacher thinks it went well.")
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert isinstance(report.student_quotes, list)
        assert len(report.student_quotes) == 2
        assert report.student_quotes[0]["sentiment"] == "positive"
        assert report.teacher_reflection == "Teacher thinks it went well."

    def test_student_quotes_can_be_empty(self, db_session: Session):
        report = self._make_report("job_def456", [], None)
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.student_quotes == []
        assert report.teacher_reflection is None

    def test_stored_dicts_validate_as_student_quotes(self, db_session: Session):
        """Dicts read back from JSON column must round-trip through StudentQuote.model_validate."""
        raw_quotes = [{"quote": "Very clear explanations.", "sentiment": "positive", "context": "Lectures"}]
        report = self._make_report("job_ghi789", raw_quotes, None)
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        parsed = [StudentQuote.model_validate(q) for q in report.student_quotes]
        assert parsed[0].quote == "Very clear explanations."
        assert parsed[0].sentiment == "positive"
        assert parsed[0].context == "Lectures"


# ---------------------------------------------------------------------------
# StudentQuote module export verification
# ---------------------------------------------------------------------------

class TestStudentQuoteExports:
    def test_import_from_models_course(self):
        from course_esum.models.course import StudentQuote as ModelsStudentQuote
        from course_esum.schemas.evaluation import StudentQuote as SchemasStudentQuote
        assert ModelsStudentQuote is SchemasStudentQuote

    def test_import_from_models_package(self):
        from course_esum.models import StudentQuote as PackageStudentQuote
        from course_esum.schemas.evaluation import StudentQuote as SchemasStudentQuote
        assert PackageStudentQuote is SchemasStudentQuote

    def test_import_from_schemas_package(self):
        from course_esum.schemas import StudentQuote as PackageStudentQuote
        from course_esum.schemas.evaluation import StudentQuote as SchemasStudentQuote
        assert PackageStudentQuote is SchemasStudentQuote


# ---------------------------------------------------------------------------
# API endpoint tests: /jobs/{id} and /history
# ---------------------------------------------------------------------------

class TestApiEndpointsStudentQuotes:
    def test_get_job_status_includes_student_quotes_and_teacher_reflection(self, client, auth_headers, session: Session):
        from datetime import datetime, timezone
        from course_esum.models.job import EvaluationJob
        from course_esum.schemas.job import JobStatus, InputType

        job = EvaluationJob(
            id="job_quotes_test_01",
            status=JobStatus.COMPLETED.value,
            input_type=InputType.COURSE_CODE.value,
            course_code="DVAE23",
            output_language="English",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(job)
        session.commit()

        report = EvaluationReport(
            job_id=job.id,
            course_code="DVAE23",
            course_name_and_code="AI Techniques (DVAE23)",
            positive_summary=["Great lectures"],
            critique_summary=["Tough exam"],
            workload="appropriate",
            trend_over_time="Improving",
            reports_analyzed=["HT2024"],
            respondents_count=20,
            registered_count=40,
            response_rate_percent=50.0,
            student_quotes=[
                {"quote": "Hands-on labs were awesome.", "sentiment": "positive", "context": "Labs"},
                {"quote": "Pacing was too fast in week 3.", "sentiment": "critique", "context": "Pacing"},
            ],
            teacher_reflection="Students engaged actively during seminars.",
        )
        session.add(report)
        session.commit()

        resp = client.get(f"/api/v1/evaluations/jobs/{job.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "COMPLETED"
        assert data["result"] is not None
        result = data["result"]
        assert len(result["student_quotes"]) == 2
        assert result["student_quotes"][0]["quote"] == "Hands-on labs were awesome."
        assert result["student_quotes"][0]["sentiment"] == "positive"
        assert result["student_quotes"][0]["context"] == "Labs"
        assert result["student_quotes"][1]["quote"] == "Pacing was too fast in week 3."
        assert result["student_quotes"][1]["sentiment"] == "critique"
        assert result["teacher_reflection"] == "Students engaged actively during seminars."
        assert result["respondents_count"] == 20
        assert result["registered_count"] == 40
        assert result["response_rate_percent"] == 50.0

    def test_get_history_includes_student_quotes_and_teacher_reflection(self, client, auth_headers, session: Session):
        from datetime import datetime, timezone
        from course_esum.models.job import EvaluationJob
        from course_esum.schemas.job import JobStatus, InputType

        job = EvaluationJob(
            id="job_quotes_test_02",
            status=JobStatus.COMPLETED.value,
            input_type=InputType.COURSE_CODE.value,
            course_code="ISGB11",
            output_language="English",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(job)
        session.commit()

        report = EvaluationReport(
            job_id=job.id,
            course_code="ISGB11",
            course_name_and_code="Information Systems (ISGB11)",
            positive_summary=["Helpful materials"],
            critique_summary=["Too many assignments"],
            workload="high",
            trend_over_time="Stable",
            reports_analyzed=["VT2024"],
            respondents_count=15,
            registered_count=30,
            response_rate_percent=50.0,
            student_quotes=[
                {"quote": "Good balance between theory and practice.", "sentiment": "positive", "context": "Content"},
            ],
            teacher_reflection="I plan to update assignment instructions next term.",
        )
        session.add(report)
        session.commit()

        resp = client.get("/api/v1/evaluations/history?course_code=ISGB11", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1

        matched = [i for i in items if i["course_name_and_code"] == "Information Systems (ISGB11)"]
        assert len(matched) == 1
        item = matched[0]
        assert len(item["student_quotes"]) == 1
        assert item["student_quotes"][0]["quote"] == "Good balance between theory and practice."
        assert item["student_quotes"][0]["sentiment"] == "positive"
        assert item["teacher_reflection"] == "I plan to update assignment instructions next term."
        assert item["respondents_count"] == 15
        assert item["registered_count"] == 30
        assert item["response_rate_percent"] == 50.0
