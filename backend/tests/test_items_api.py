from app.models import Item, Job, JobStatus, SourceType, Tag

PDF_BYTES = b"%PDF-1.4\n%fake but starts like a pdf\n"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_save_url_queues_a_job(client, session):
    resp = client.post("/items", data={"url": "https://example.com/post"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["source_type"] == "url"
    assert body["status"] == "queued"
    jobs = session.query(Job).all()
    assert [(j.item_id, j.status) for j in jobs] == [(body["id"], JobStatus.queued)]


def test_save_pdf_stores_file(client, tmp_path):
    resp = client.post(
        "/items", files={"file": ("db_indexing_notes.pdf", PDF_BYTES, "application/pdf")}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["title"] == "db indexing notes"
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_rejects_non_pdf(client):
    resp = client.post("/items", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 415


def test_requires_exactly_one_source(client):
    assert client.post("/items").status_code == 422
    resp = client.post(
        "/items",
        data={"url": "https://example.com"},
        files={"file": ("a.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 422


def test_rejects_bad_url(client):
    assert client.post("/items", data={"url": "not a url"}).status_code == 422


def _seed(session):
    db, ml = Tag(name="databases"), Tag(name="ml")
    a = Item(title="Indexing", source_type=SourceType.url, source="https://a", tags=[db])
    b = Item(title="Transformers", source_type=SourceType.url, source="https://b", tags=[ml])
    c = Item(title="Vector DBs", source_type=SourceType.url, source="https://c", tags=[db, ml])
    session.add_all([a, b, c])
    session.commit()


def test_filter_by_tag(client, session):
    _seed(session)
    titles = {i["title"] for i in client.get("/items", params={"tag": "databases"}).json()}
    assert titles == {"Indexing", "Vector DBs"}
    assert len(client.get("/items").json()) == 3


def test_get_item_and_404(client, session):
    _seed(session)
    first = client.get("/items").json()[0]
    assert client.get(f"/items/{first['id']}").json()["title"] == first["title"]
    assert client.get("/items/9999").status_code == 404


def test_tags_with_counts(client, session):
    _seed(session)
    assert client.get("/tags").json() == [
        {"id": 1, "name": "databases", "item_count": 2},
        {"id": 2, "name": "ml", "item_count": 2},
    ]


def test_ask_not_built_yet(client):
    assert client.post("/ask", json={"question": "what?"}).status_code == 501
