import pymupdf

from app.models import Item, ItemImage, SourceType
from app.pipeline import process_item
from app.services import images
from app.services.embeddings import HashingEmbedder
from app.sources import ExtractedDoc, PageText
from tests.helpers import FakeLLM

TEXT = "Melatonin rises at night.\n\nBright light delays it.\n\nAlcohol fragments sleep."


def png(width=400, height=300, shade=180) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.clear_with(shade)
    return pix.tobytes("png")


class StubSource:
    def __init__(self, doc):
        self.doc = doc

    def extract(self, item):
        return self.doc


def test_pictures_are_reencoded_scaled_and_checked():
    picture = images.normalize(png(3200, 1600))
    assert picture.mime == "image/jpeg" and (picture.width, picture.height) == (1600, 800)
    assert picture.data[:3] == b"\xff\xd8\xff"  # JPEG, whatever came in
    assert images.normalize(b"not a picture") is None
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        b'<script>alert(1)</script><rect width="200" height="200"/></svg>'
    )
    rendered = images.normalize(svg)
    assert rendered is not None and rendered.data[:3] == b"\xff\xd8\xff"  # flattened, no script


def test_upload_and_serve_only_to_the_owner(client, anon_client):
    made = client.post(
        "/images", files={"file": ("a.png", png(), "image/png")}, data={"alt": "A chart"}
    )
    assert made.status_code == 201
    body = made.json()
    assert body["url"] == f"/images/{body['id']}" and body["alt"] == "A chart"
    served = client.get(body["url"])
    assert served.headers["content-type"] == "image/jpeg"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert anon_client.get(body["url"]).status_code == 401
    bad = client.post("/images", files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad.status_code == 422


def test_figures_and_cover_are_placed_in_the_text(client, session, user):
    item = Item(user_id=user.id, title="Sleep", source_type=SourceType.url, source="https://x")
    session.add(item)
    session.commit()
    doc = ExtractedDoc(
        title="Sleep",
        pages=[PageText(None, TEXT)],
        images=[
            images.ExtractedImage(role="cover", url="https://x/cover.jpg"),
            images.ExtractedImage(
                role="figure",
                data=png(),
                alt="Melatonin over a day",
                anchor="Melatonin rises at night.",
            ),
            images.ExtractedImage(role="figure", data=png(40, 40)),  # an icon: skipped
            images.ExtractedImage(role="figure", url="https://x/missing.jpg"),  # can't fetch
        ],
    )
    fetched = []

    def fetch(url):
        fetched.append(url)
        return png(800, 450) if url.endswith("cover.jpg") else None

    for _ in range(2):  # reading it again replaces its pictures rather than adding more
        process_item(
            session,
            item,
            embedder=HashingEmbedder(),
            llm=FakeLLM(),
            source=StubSource(doc),
            fetch_image=fetch,
        )
        session.commit()
    rows = session.query(ItemImage).filter_by(item_id=item.id).all()
    assert sorted(r.role for r in rows) == ["cover", "figure"]
    figure = next(r for r in rows if r.role == "figure")
    assert figure.position == TEXT.index("\n\n") and figure.alt == "Melatonin over a day"

    shown = client.get(f"/items/{item.id}").json()
    cover = next(r for r in rows if r.role == "cover")
    assert shown["cover_url"] == f"/images/{cover.id}"
    content = client.get(f"/items/{item.id}/content").json()
    assert [i["id"] for i in content["images"]] == [figure.id]

    # An answer citing the first paragraph gets the figure placed after it.
    sources = [{"item_id": item.id, "start_char": 0, "end_char": 25, "page": None}]
    images.images_near(session, sources)
    assert [i["id"] for i in sources[0]["images"]] == [figure.id]

    # Deleting the item deletes its pictures' files too.
    keys = [r.key for r in rows]
    client.delete(f"/items/{item.id}")
    assert all(images.files.read(k) is None for k in keys)


def test_pictures_added_to_a_note_are_shown_where_they_were_added(client, session, user):
    upload = client.post("/images", files={"file": ("a.png", png(), "image/png")}).json()
    text = f"Sleep plan.\n\n![My chart](image:{upload['id']})\n\nNo coffee after noon."
    note = client.post("/items", data={"text": text, "title": "Plan"}).json()
    item = session.get(Item, note["id"])
    process_item(session, item, embedder=HashingEmbedder(), llm=FakeLLM())
    session.commit()
    content = client.get(f"/items/{item.id}/content").json()
    assert "image:" not in content["pages"][0]["text"]
    placed = content["images"][0]
    assert placed["id"] == upload["id"] and placed["position"] == len("Sleep plan.")
    assert client.get(f"/items/{item.id}").json()["cover_url"] == f"/images/{upload['id']}"


def test_someone_elses_picture_cant_be_claimed_by_a_note(client, session, user):
    from app.models import User

    other = User(email="x@example.com", password_hash="x")
    session.add(other)
    session.flush()
    stranger = images.store(session, other.id, images.normalize(png()), role="upload")
    session.commit()
    note = client.post("/items", data={"text": f"Hi\n\n![x](image:{stranger.id})"}).json()
    item = session.get(Item, note["id"])
    process_item(session, item, embedder=HashingEmbedder(), llm=FakeLLM())
    session.commit()
    session.refresh(stranger)
    assert stranger.item_id is None
