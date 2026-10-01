"""Tests for the orphaned job sweeper that runs at application startup."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool

from course_esum.models.job import EvaluationJob
from course_esum.schemas.job import JobStatus
from course_esum.core.startup import sweep_orphaned_jobs, ORPHAN_ERROR_MSG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    """Return a fresh in-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def seed_job(session: Session, status: str, course_code: str = "TEST101") -> EvaluationJob:
    job = EvaluationJob(status=status, course_code=course_code)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def fetch_job(session: Session, job_id: str) -> EvaluationJob:
    return session.get(EvaluationJob, job_id)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSweepOrphanedJobs:

    def test_sweep_marks_processing_as_failed(self):
        """PROCESSING jobs are updated to FAILED with message and timestamp."""
        engine = make_engine()
        with Session(engine) as session:
            job1 = seed_job(session, JobStatus.PROCESSING.value, course_code="A101")
            job2 = seed_job(session, JobStatus.PROCESSING.value, course_code="B202")
            # Capture IDs now — session.close() expires all attributes.
            id1, id2 = job1.id, job2.id

        sweep_orphaned_jobs(target_engine=engine)

        with Session(engine) as session:
            j1 = fetch_job(session, id1)
            j2 = fetch_job(session, id2)

            assert j1.status == JobStatus.FAILED.value
            assert j1.error_message == ORPHAN_ERROR_MSG
            assert j1.completed_at is not None

            assert j2.status == JobStatus.FAILED.value
            assert j2.error_message == ORPHAN_ERROR_MSG
            assert j2.completed_at is not None

    def test_sweep_leaves_completed_and_failed_untouched(self):
        """Jobs already in COMPLETED or FAILED status must not be modified."""
        engine = make_engine()
        with Session(engine) as session:
            completed = seed_job(session, JobStatus.COMPLETED.value, course_code="C303")
            failed    = seed_job(session, JobStatus.FAILED.value,    course_code="D404")
            cid, fid  = completed.id, failed.id

        sweep_orphaned_jobs(target_engine=engine)

        with Session(engine) as session:
            c = fetch_job(session, cid)
            f = fetch_job(session, fid)

            assert c.status == JobStatus.COMPLETED.value
            assert c.error_message is None
            assert c.completed_at is None  # was not set by sweeper

            assert f.status == JobStatus.FAILED.value
            assert f.error_message is None   # original value preserved
            assert f.completed_at is None

    def test_sweep_mixed_statuses(self):
        """Only PROCESSING jobs are swept; COMPLETED and FAILED remain unchanged."""
        engine = make_engine()
        with Session(engine) as session:
            orphan    = seed_job(session, JobStatus.PROCESSING.value, course_code="E505")
            completed = seed_job(session, JobStatus.COMPLETED.value,  course_code="F606")
            failed    = seed_job(session, JobStatus.FAILED.value,     course_code="G707")
            oid, cid, fid = orphan.id, completed.id, failed.id

        sweep_orphaned_jobs(target_engine=engine)

        with Session(engine) as session:
            o = fetch_job(session, oid)
            c = fetch_job(session, cid)
            f = fetch_job(session, fid)

            # Orphaned job updated
            assert o.status == JobStatus.FAILED.value
            assert o.error_message == ORPHAN_ERROR_MSG
            assert o.completed_at is not None

            # Others untouched
            assert c.status == JobStatus.COMPLETED.value
            assert f.status == JobStatus.FAILED.value
            assert f.error_message is None

    def test_sweep_no_orphans_is_noop(self):
        """When no PROCESSING jobs exist the sweeper completes without error."""
        engine = make_engine()
        # Empty DB — should not raise
        sweep_orphaned_jobs(target_engine=engine)

        with Session(engine) as session:
            all_jobs = session.exec(
                __import__("sqlmodel", fromlist=["select"]).select(EvaluationJob)
            ).all()
        assert all_jobs == []

    def test_sweep_db_error_does_not_raise(self):
        """A DB failure during the sweep must be swallowed so the server boots."""
        broken_engine = MagicMock()
        broken_engine.__class__ = __import__(
            "sqlalchemy", fromlist=["Engine"]
        ).Engine
        # Simulate Session(engine) raising immediately
        with patch(
            "course_esum.core.startup.Session",
            side_effect=Exception("DB connection refused"),
        ):
            # Must not propagate — server boot should continue
            sweep_orphaned_jobs(target_engine=broken_engine)
