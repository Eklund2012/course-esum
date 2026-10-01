import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Engine
from sqlmodel import Session, select

from course_esum.models.job import EvaluationJob
from course_esum.schemas.job import JobStatus
from course_esum.core.database import engine as _default_engine

logger = logging.getLogger(__name__)

ORPHAN_ERROR_MSG = "Job interrupted due to unexpected server restart/shutdown."


def sweep_orphaned_jobs(target_engine: Optional[Engine] = None) -> None:
    """Find all jobs stuck in PROCESSING status and mark them FAILED.

    Called during application startup so that jobs orphaned by a previous
    crash or forced restart do not remain permanently stuck.

    Args:
        target_engine: SQLAlchemy engine to use.  Defaults to the application's
            global engine.  Pass an explicit engine in tests to avoid
            monkeypatching module-level state.

    Note:
        Wrapped in a broad try/except so a DB failure never prevents the
        server from booting.
    """
    db_engine = target_engine if target_engine is not None else _default_engine
    try:
        with Session(db_engine) as session:
            statement = select(EvaluationJob).where(
                EvaluationJob.status == JobStatus.PROCESSING.value
            )
            orphans = session.exec(statement).all()

            if not orphans:
                logger.debug("Orphaned job sweep: no stuck jobs found.")
                return

            now = datetime.now(timezone.utc)
            for job in orphans:
                job.status = JobStatus.FAILED.value
                job.error_message = ORPHAN_ERROR_MSG
                job.completed_at = now
                session.add(job)

            session.commit()
            logger.warning(
                "Orphaned job sweep: marked %d job(s) as FAILED.", len(orphans)
            )
    except Exception:
        logger.exception(
            "Orphaned job sweep failed — server will still start normally."
        )
