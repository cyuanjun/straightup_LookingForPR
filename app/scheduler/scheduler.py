"""APScheduler setup with SQLAlchemy job store (Postgres-backed, persistent).

Started explicitly by FastAPI startup *after* application.start(). Stop in shutdown.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone=ZoneInfo(settings.tz),
            jobstores={
                "default": SQLAlchemyJobStore(url=settings.database_url),
            },
            executors={
                "default": AsyncIOExecutor(),
            },
            job_defaults={
                "coalesce": True,
                "misfire_grace_time": 60,
                "max_instances": 1,
            },
        )
        _scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return _scheduler


def _on_job_error(event: JobExecutionEvent) -> None:
    import logging

    logging.getLogger("app.scheduler").exception(
        "APScheduler job failed: id=%s, exception=%s", event.job_id, event.exception
    )
