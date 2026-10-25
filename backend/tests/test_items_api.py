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


def _seed(session, user):
    db, ml = Tag(name="databases", user_id=user.id), Tag(name="ml", user_id=user.id)
    common = {"user_id": user.id, "source_type": SourceType.url}
    a = Item(title="Indexing", source="https://a", tags=[db], **common)
    b = Item(title="Transformers", source="https://b", tags=[ml], **common)
    c = Item(title="Vector DBs", source="https://c", tags=[db, ml], **common)
    session.add_all([a, b, c])
    session.commit()


def test_filter_by_tag(client, session, user):
    _seed(session, user)
    titles = {i["title"] for i in client.get("/items", params={"tag": "databases"}).json()}
    assert titles == {"Indexing", "Vector DBs"}
    assert len(client.get("/items").json()) == 3


def test_get_item_and_404(client, session, user):
    _seed(session, user)
    first = client.get("/items").json()[0]
    assert client.get(f"/items/{first['id']}").json()["title"] == first["title"]
    assert client.get("/items/9999").status_code == 404


def test_tags_with_counts(client, session, user):
    _seed(session, user)
    assert client.get("/tags").json() == [
        {"id": 1, "name": "databases", "item_count": 2},
        {"id": 2, "name": "ml", "item_count": 2},
    ]


def test_reprocess_requeues_a_failed_item(client, session, user):
    item = Item(
        user_id=user.id, title="t", source_type=SourceType.url, source="https://x", status="failed"
    )
    session.add(item)
    session.commit()
    resp = client.post(f"/items/{item.id}/reprocess")
    assert resp.status_code == 202 and resp.json()["status"] == "queued"
    assert client.post(f"/items/{item.id}/reprocess").status_code == 409  # already queued


def test_delete_removes_item_and_file(client, tmp_path):
    item = client.post("/items", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")}).json()
    assert client.get(f"/items/{item['id']}/file").content == PDF_BYTES
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404
    assert list(tmp_path.glob("*.pdf")) == []


def test_url_item_has_no_file(client):
    item = client.post("/items", data={"url": "https://example.com/post"}).json()
    assert client.get(f"/items/{item['id']}/file").status_code == 404


def test_user_can_set_tags(client, session, user):
    _seed(session, user)
    item_id = client.get("/items", params={"tag": "ml"}).json()[0]["id"]
    resp = client.put(f"/items/{item_id}/tags", json={"tags": ["Reading List", "ml", "ML!", " "]})
    body = resp.json()
    assert resp.status_code == 200
    assert sorted(t["name"] for t in body["tags"]) == ["ml", "reading list"]
    assert body["tags_edited"] is True
    assert {"name": "reading list", "item_count": 1}.items() <= {
        k: v
        for t in client.get("/tags").json()
        if t["name"] == "reading list"
        for k, v in t.items()
    }.items()


def test_removing_a_tag_everywhere_drops_it_from_the_tag_list(client, session, user):
    _seed(session, user)
    for item in client.get("/items", params={"tag": "ml"}).json():
        client.put(f"/items/{item['id']}/tags", json={"tags": []})
    assert "ml" not in {t["name"] for t in client.get("/tags").json()}


def test_tag_list_is_capped(client, session, user):
    _seed(session, user)
    item_id = client.get("/items").json()[0]["id"]
    resp = client.put(f"/items/{item_id}/tags", json={"tags": [f"t{i}" for i in range(13)]})
    assert resp.status_code == 422


def test_signed_out_requests_are_refused(anon_client):
    for path in ("/items", "/tags", "/chats", "/auth/me"):
        assert anon_client.get(path).status_code == 401


def test_people_only_see_their_own_library(client, anon_client, session, user):
    _seed(session, user)
    other = anon_client
    assert (
        other.post(
            "/auth/signup", json={"email": "other@example.com", "password": "password1"}
        ).status_code
        == 201
    )
    assert other.get("/items").json() == []
    assert other.get("/tags").json() == []
    mine = client.get("/items").json()[0]["id"]
    assert other.get(f"/items/{mine}").status_code == 404
    assert other.delete(f"/items/{mine}").status_code == 404
    assert other.put(f"/items/{mine}/tags", json={"tags": ["x"]}).status_code == 404
    # the same tag name is separate per person
    item = other.post("/items", data={"url": "https://example.com/p"}).json()
    other.put(f"/items/{item['id']}/tags", json={"tags": ["databases"]})
    assert [t["item_count"] for t in client.get("/tags").json() if t["name"] == "databases"] == [2]
