"""A small job queue on top of Postgres.

Workers claim the oldest queued job with FOR UPDATE SKIP LOCKED, so several workers can run
at once without taking the same job, and no extra broker (Redis, RabbitMQ) is needed.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, ItemStatus, Job, JobStatus

MAX_ATTEMPTS = 3


def enqueue(session: Session, item: Item) -> Job:
    job = Job(item_id=item.id, status=JobStatus.queued)
    session.add(job)
    return job


def claim_next(session: Session) -> Job | None:
    """Claim one queued job and mark it running. Caller commits."""
    job = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        return None
    job.status = JobStatus.running
    job.attempts += 1
    item = session.get(Item, job.item_id)
    if item is not None:
        item.status = ItemStatus.processing
    return job


def complete(session: Session, job: Job) -> None:
    job.status = JobStatus.done
    item = session.get(Item, job.item_id)
    if item is not None:
        item.status = ItemStatus.ready
        item.error = None


def fail(session: Session, job: Job, error: str, *, retryable: bool = True) -> None:
    """Record a failure. Retryable jobs go back to the queue until MAX_ATTEMPTS."""
    job.error = error
    item = session.get(Item, job.item_id)
    if retryable and job.attempts < MAX_ATTEMPTS:
        job.status = JobStatus.queued
        if item is not None:
            item.status = ItemStatus.queued
        return
    job.status = JobStatus.failed
    if item is not None:
        item.status = ItemStatus.failed
        item.error = error
