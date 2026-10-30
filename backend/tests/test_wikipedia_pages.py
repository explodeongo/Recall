from sqlalchemy import update

from app.config import get_settings
from app.models import Item, ItemStatus, SourceType
from app.pipeline import process_item
from app.services import files
from app.services.embeddings import HashingEmbedder
from app.sources import ExtractedDoc, PageText
from app.sources.wikipedia import pdf_url
from tests.test_guest import _guest

PAGES_PDF = b"%PDF-1.7\n%Wikipedia's printable version\n"
ARTICLE = "https://en.wikipedia.org/wiki/Spaced_repetition"


class StubSource:
    def extract(self, item):
        return ExtractedDoc(title=None, pages=[PageText(None, "Spaced repetition " * 20)])


def _read(session, user, link: str, fetched: bytes | None = PAGES_PDF) -> Item:
    item = Item(user_id=user.id, title="Spacing", source_type=SourceType.url, source=link)
    session.add(item)
    session.flush()
    asked = []

    def fetch_pages(url):
        asked.append(url)
        return fetched

    process_item(
        session,
        item,
        embedder=HashingEmbedder(),
        llm=None,
        source=StubSource(),
        fetch_pages=fetch_pages,
    )
    item.status = ItemStatus.ready
    session.commit()
    assert asked == [link]
    return item


def test_wikipedia_articles_map_to_their_printable_pdf():
    assert pdf_url(ARTICLE) == "https://en.wikipedia.org/api/rest_v1/page/pdf/Spaced_repetition"
    assert pdf_url("https://de.m.wikipedia.org/wiki/Tf%E2%80%93idf#Formel") == (
        "https://de.wikipedia.org/api/rest_v1/page/pdf/Tf%E2%80%93idf"
    )
    assert pdf_url("https://en.wikipedia.org/wiki/A/B_testing").endswith("/pdf/A%2FB_testing")
    assert pdf_url("https://example.com/wiki/Spaced_repetition") is None
    assert pdf_url("https://en.wikipedia.org/w/index.php?title=Spaced_repetition") is None


def test_a_wikipedia_link_keeps_its_pdf_for_the_read_tab(client, session, user, tmp_path):
    item = _read(session, user, ARTICLE)
    shown = client.get(f"/items/{item.id}").json()
    assert shown["has_pages"] is True and "pages_file" not in shown
    resp = client.get(f"/items/{item.id}/file")
    assert resp.content == PAGES_PDF and resp.headers["content-type"] == "application/pdf"

    # Reading it again keeps the PDF it has rather than fetching another.
    kept = item.pages_file
    process_item(session, item, embedder=HashingEmbedder(), llm=None, source=StubSource())
    session.commit()
    assert item.pages_file == kept

    assert client.delete(f"/items/{item.id}").status_code == 204
    assert list(tmp_path.glob("*.pdf")) == []


def test_without_a_pdf_the_link_reads_as_text(client, session, user):
    item = _read(session, user, "https://example.com/post", fetched=None)
    assert client.get(f"/items/{item.id}").json()["has_pages"] is False
    assert client.get(f"/items/{item.id}/file").status_code == 404


def test_guests_share_the_templates_page_pdfs(client, session, user, monkeypatch):
    monkeypatch.setattr(get_settings(), "guest_template_email", "me@example.com")
    item = _read(session, user, ARTICLE)
    session.execute(update(Item).values(status=ItemStatus.ready))
    session.commit()
    visitor = _guest()
    copy = next(i for i in visitor.get("/items").json() if i["source"] == ARTICLE)
    assert copy["has_pages"] is True
    assert visitor.get(f"/items/{copy['id']}/file").content == PAGES_PDF
    assert visitor.delete(f"/items/{copy['id']}").status_code == 204
    assert files.read(session.get(Item, item.id).pages_file) == PAGES_PDF  # still the template's
