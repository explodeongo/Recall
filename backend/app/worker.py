"""Background worker: python -m app.worker"""

import logging
import threading
import time

import httpx

from app import pipeline
from app.db import SessionLocal
from app.models import Item
from app.services import jobs
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, LLMError, get_llm

log = logging.getLogger("recall.worker")


def run_once(embedder: Embedder, llm: LLMClient | None = None) -> bool:
    """Process one job. Returns False when no job is due.

    `llm` is built per job when not given, so a key added to .env is picked up by a retry
    without restarting the worker.
    """
    with SessionLocal() as session:
        job = jobs.claim_next(session)
        if job is None:
            return False
        session.commit()
        item = session.get(Item, job.item_id)
        started = time.perf_counter()
        try:
            if item is not None:
                pipeline.process_item(
                    session, item, embedder=embedder, llm=llm if llm is not None else get_llm()
                )
            jobs.complete(session, job)
            log.info("item %s ready in %.1fs", job.item_id, time.perf_counter() - started)
        except pipeline.PermanentError as exc:
            session.rollback()
            log.warning("item %s failed: %s", job.item_id, exc)
            jobs.fail(session, job, str(exc), retryable=False)
        except LLMError as exc:
            session.rollback()
            log.warning("item %s: LLM error: %s", job.item_id, exc)
            jobs.fail(session, job, str(exc), retryable=exc.retryable)
        except httpx.HTTPError as exc:
            session.rollback()
            log.warning("item %s: fetch error: %s", job.item_id, exc)
            jobs.fail(session, job, f"Couldn't fetch the page: {exc}")
        except Exception as exc:
            log.exception("job %s failed", job.id)
            session.rollback()
            jobs.fail(session, job, f"Unexpected error while processing: {exc}")
        session.commit()
        return True


def run_forever(stop: threading.Event | None = None, poll_seconds: float = 1.0) -> None:
    log.info("loading embedding model")
    embedder = get_embedder()
    with SessionLocal() as session:
        if filled := pipeline.backfill_summary_embeddings(session, embedder):
            log.info("embedded the summaries of %s older items", filled)
    log.info("worker started")
    while stop is None or not stop.is_set():
        try:
            busy = run_once(embedder)
        except Exception:  # a database hiccup shouldn't kill the loop
            log.exception("worker loop error")
            busy = False
        if not busy:
            if stop is not None:
                stop.wait(poll_seconds)
            else:
                time.sleep(poll_seconds)


def start_in_background() -> threading.Event:
    """Run the worker on a thread of the current process (RUN_WORKER_IN_API). Returns the event
    that stops it."""
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), name="recall-worker", daemon=True).start()
    return stop


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_forever()


if __name__ == "__main__":
    main()
