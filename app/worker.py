import logging
import signal
import time

from .config import settings
from .database import SessionLocal
from .observability import configure_logging
from .services.jobs import claim_next_job, execute_job, recover_stale_jobs
from .services.schedules import enqueue_due_schedules


logger = logging.getLogger(__name__)
stopping = False


def _stop(_signum, _frame) -> None:
    global stopping
    stopping = True


def run() -> None:
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with SessionLocal() as db:
        recovered = recover_stale_jobs(db)
        if recovered:
            logger.warning("recovered stale background jobs", extra={"count": recovered})
    while not stopping:
        with SessionLocal() as db:
            enqueue_due_schedules(db, settings.worker_schedule_batch_size)
            job = claim_next_job(db)
            if job:
                logger.info("running background job", extra={"job_id": job.job_id, "job_type": job.job_type})
                execute_job(db, job)
                continue
        time.sleep(settings.worker_poll_seconds)
if __name__ == "__main__":
    run()
