"""Background worker: python -m app.worker"""

import logging
import time

from app import pipeline
from app.db import SessionLocal
from app.models import Item
from app.services import jobs

log = logging.getLogger("recall.worker")


def run_once() -> bool:
    """Process one job. Returns False when the queue is empty."""
    with SessionLocal() as session:
        job = jobs.claim_next(session)
        if job is None:
            return False
        session.commit()
        item = session.get(Item, job.item_id)
        try:
            if item is not None:
                pipeline.process_item(session, item)
            jobs.complete(session, job)
        except pipeline.PermanentError as exc:
            session.rollback()
            jobs.fail(session, job, str(exc), retryable=False)
        except Exception as exc:
            log.exception("job %s failed", job.id)
            session.rollback()
            jobs.fail(session, job, str(exc))
        session.commit()
        return True


def main(poll_seconds: float = 1.0) -> None:
    logging.basicConfig(level=logging.INFO)
    log.info("worker started")
    while True:
        if not run_once():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
