"""A small job queue on top of Postgres.

Workers claim the oldest queued job with FOR UPDATE SKIP LOCKED, so several workers can run
at once without taking the same job, and no extra broker (Redis, RabbitMQ) is needed.

Failed jobs are retried with a growing delay (`run_after`). A job left `running` by a worker
that crashed is picked up again once it has been untouched for STALE_AFTER.
"""

from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Item, ItemStatus, Job, JobStatus

MAX_ATTEMPTS = 3
RETRY_BASE = timedelta(seconds=15)
STALE_AFTER = timedelta(minutes=10)


def enqueue(session: Session, item: Item) -> Job:
    job = Job(item_id=item.id, status=JobStatus.queued)
    session.add(job)
    item.status = ItemStatus.queued
    item.error = None
    return job


def claim_next(session: Session) -> Job | None:
    """Claim one due job and mark it running. Caller commits."""
    now = func.now()
    job = session.scalars(
        select(Job)
        .where(
            or_(
                and_(Job.status == JobStatus.queued, Job.run_after <= now),
                and_(Job.status == JobStatus.running, Job.updated_at < now - STALE_AFTER),
            )
        )
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        return None
    job.status = JobStatus.running
    job.attempts += 1
    job.updated_at = now
    item = session.get(Item, job.item_id)
    if item is not None:
        item.status = ItemStatus.processing
    return job


def complete(session: Session, job: Job) -> None:
    job.status = JobStatus.done
    job.error = None
    item = session.get(Item, job.item_id)
    if item is not None:
        item.status = ItemStatus.ready
        item.error = None


def fail(session: Session, job: Job, error: str, *, retryable: bool = True) -> None:
    """Record a failure. Retryable jobs go back to the queue, later each time, until
    MAX_ATTEMPTS."""
    job.error = error
    item = session.get(Item, job.item_id)
    if retryable and job.attempts < MAX_ATTEMPTS:
        job.status = JobStatus.queued
        job.run_after = func.now() + RETRY_BASE * (2 ** (job.attempts - 1))
        if item is not None:
            item.status = ItemStatus.queued
        return
    job.status = JobStatus.failed
    if item is not None:
        item.status = ItemStatus.failed
        item.error = error
