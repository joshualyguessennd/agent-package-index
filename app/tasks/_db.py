"""Standalone database session for Celery tasks (outside Flask app context)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.config import Config

_engine = create_engine(Config.DATABASE_URL, pool_pre_ping=True)
_session_factory = sessionmaker(bind=_engine)
task_session: scoped_session[Session] = scoped_session(_session_factory)


def get_task_session() -> scoped_session[Session]:
    """Return the scoped session for use in Celery tasks."""
    return task_session


def remove_task_session() -> None:
    """Remove the current scoped session (call at end of task)."""
    task_session.remove()
