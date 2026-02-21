from celery import Celery
from celery.schedules import crontab

from app.config import Config

celery_app = Celery("agent_system")
celery_app.conf.update(
    broker_url=Config.REDIS_URL,
    result_backend=Config.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Package list crawl every 6 hours
        "crawl-pypi-list": {
            "task": "crawl_pypi_package_list",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "crawl-npm-list": {
            "task": "crawl_npm_package_list",
            "schedule": crontab(minute=15, hour="*/6"),
        },
        # Downloads daily at 2-3 AM
        "crawl-pypi-downloads": {
            "task": "crawl_pypi_downloads_batch",
            "schedule": crontab(minute=0, hour=2),
            "args": [[]],
        },
        "crawl-npm-downloads": {
            "task": "crawl_npm_downloads_batch",
            "schedule": crontab(minute=30, hour=2),
            "args": [[]],
        },
        # Vulnerabilities weekly (Monday 3 AM)
        "crawl-vulnerabilities": {
            "task": "crawl_vulnerabilities_batch",
            "schedule": crontab(minute=0, hour=3, day_of_week=1),
        },
        # Score recompute daily at 5 AM
        "recompute-scores": {
            "task": "recompute_all_scores",
            "schedule": crontab(minute=0, hour=5),
        },
    },
)

# Auto-discover tasks in app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])
