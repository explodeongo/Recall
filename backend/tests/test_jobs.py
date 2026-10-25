from sqlalchemy import func, update

from app.db import SessionLocal
from app.models import Item, ItemStatus, Job, JobStatus, SourceType
from app.services import jobs


def _item_with_job(session):
    item = Item(title="t", source_type=SourceType.url, source="https://x")
    session.add(item)
    session.flush()
    job = jobs.enqueue(session, item)
    session.commit()
    return item, job


def test_claim_complete(session):
    item, _ = _item_with_job(session)
    job = jobs.claim_next(session)
    assert job.status == JobStatus.running and job.attempts == 1
    assert session.get(Item, item.id).status == ItemStatus.processing
    jobs.complete(session, job)
    session.commit()
    assert session.get(Item, item.id).status == ItemStatus.ready
    assert jobs.claim_next(session) is None


def test_retry_then_fail(session):
    item, _ = _item_with_job(session)
    for attempt in range(1, jobs.MAX_ATTEMPTS + 1):
        job = jobs.claim_next(session)
        assert job.attempts == attempt
        jobs.fail(session, job, "boom")
        session.commit()
        _make_due(session)
    assert job.status == JobStatus.failed
    assert session.get(Item, item.id).status == ItemStatus.failed
    assert session.get(Item, item.id).error == "boom"


def test_permanent_failure_skips_retry(session):
    item, _ = _item_with_job(session)
    job = jobs.claim_next(session)
    jobs.fail(session, job, "no text layer", retryable=False)
    session.commit()
    assert job.status == JobStatus.failed and job.attempts == 1


def test_two_workers_never_claim_the_same_job(session):
    _item_with_job(session)
    _item_with_job(session)
    with SessionLocal() as w1, SessionLocal() as w2:
        j1 = jobs.claim_next(w1)  # holds its row lock until commit
        j2 = jobs.claim_next(w2)
        assert j1 is not None and j2 is not None
        assert j1.id != j2.id
        w1.commit()
        w2.commit()


def _make_due(session):
    session.execute(update(Job).values(run_after=func.now()))
    session.commit()


def test_retry_waits_for_backoff(session):
    _item_with_job(session)
    job = jobs.claim_next(session)
    jobs.fail(session, job, "rate limited")
    session.commit()
    assert job.status == JobStatus.queued
    assert jobs.claim_next(session) is None  # not due yet
    _make_due(session)
    assert jobs.claim_next(session).id == job.id


def test_reclaims_job_from_crashed_worker(session):
    _item_with_job(session)
    job = jobs.claim_next(session)
    session.commit()
    assert jobs.claim_next(session) is None  # still owned by its worker
    session.execute(update(Job).values(updated_at=func.now() - jobs.STALE_AFTER - jobs.RETRY_BASE))
    session.commit()
    again = jobs.claim_next(session)
    assert again.id == job.id and again.attempts == 2
