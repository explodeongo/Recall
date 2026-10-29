from pathlib import Path

import httpx
import pytest

from app.errors import PermanentError
from app.models import Item, SourceType
from app.services.text import clean_pages
from app.sources.pdf import PdfSource, extract_pdf_bytes
from app.sources.url import UrlSource
from tests.helpers import make_pdf

ARTICLE = (Path(__file__).parent / "fixtures" / "article.html").read_bytes()


def _pdf_item(tmp_path, data: bytes) -> Item:
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)
    return Item(title="doc", source_type=SourceType.pdf, source=str(path))


def test_pdf_text_keeps_page_numbers(tmp_path):
    data = make_pdf([["Hash indexes are fast."], ["B-trees support range scans."]], title="Notes")
    doc = PdfSource().extract(_pdf_item(tmp_path, data))
    assert doc.title == "Notes"
    assert [p.page for p in doc.pages] == [1, 2]
    assert "Hash indexes" in doc.pages[0].text and "B-trees" in doc.pages[1].text


def test_pdf_junk_metadata_title_is_ignored():
    assert extract_pdf_bytes(make_pdf([["x"]], title="Microsoft Word - draft3.docx")).title is None


def test_pdf_with_no_text_layer_is_empty_after_cleaning():
    doc = extract_pdf_bytes(make_pdf([[], []]))  # only page-number footers
    assert all(not p.text for p in clean_pages(doc.pages))


def test_corrupt_pdf_is_a_permanent_error():
    with pytest.raises(PermanentError, match="couldn't be opened"):
        extract_pdf_bytes(b"%PDF-1.4 this is not really a pdf")


def _url_source(handler) -> UrlSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return UrlSource(client=client, resolve=lambda host: ["93.184.216.34"])


def _url_item(url="https://blog.example.com/indexes") -> Item:
    return Item(title=url, source_type=SourceType.url, source=url)


def test_url_extracts_article_without_boilerplate():
    source = _url_source(
        lambda req: httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
    )
    doc = source.extract(_url_item())
    text = doc.pages[0].text
    assert doc.title == "B-trees vs hash indexes"
    assert "range queries" in text
    assert "Cookie settings" not in text and "Subscribe" not in text
    assert "\n\n" in text  # paragraphs kept apart


def test_url_read_up_to_keeps_the_start_of_a_long_page(monkeypatch):
    long_page = b"<html><body><article>" + b"<p>Early words about indexes.</p>" * 20
    long_page += b"<p>Words far down the page.</p>" * 50_000 + b"</article></body></html>"
    monkeypatch.setattr("app.sources.url.get_settings", lambda: _settings_with(max_fetch_mb=1))
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, content=long_page, headers={"content-type": "text/html"}
            )
        )
    )

    with pytest.raises(PermanentError, match="larger than 1 MB"):
        UrlSource(client=client, resolve=lambda host: ["93.184.216.34"]).extract(_url_item())
    doc = UrlSource(client=client, resolve=lambda host: ["93.184.216.34"], read_up_to=600).extract(
        _url_item()
    )
    assert "Early words" in doc.pages[0].text
    assert "far down" not in doc.pages[0].text


def _settings_with(**changes):
    from app.config import get_settings

    return get_settings().model_copy(update=changes)


def test_url_serving_a_pdf_is_read_as_pdf():
    pdf = make_pdf([["Page one text."], ["Page two text."]])
    source = _url_source(
        lambda req: httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    )
    doc = source.extract(_url_item("https://arxiv.example.org/pdf/1234"))
    assert [p.page for p in doc.pages] == [1, 2]


def test_url_follows_redirects():
    def handler(req):
        if req.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})

    doc = _url_source(handler).extract(_url_item("https://blog.example.com/old"))
    assert "hash index" in doc.pages[0].text


@pytest.mark.parametrize(
    ("status", "message"), [(403, "refused access"), (404, "wasn't found"), (410, "error")]
)
def test_url_client_errors_are_permanent(status, message):
    source = _url_source(lambda req: httpx.Response(status))
    with pytest.raises(PermanentError, match=message):
        source.extract(_url_item())


def test_url_server_errors_are_retryable():
    source = _url_source(lambda req: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        source.extract(_url_item())


def test_url_page_with_no_article_text():
    source = _url_source(lambda req: httpx.Response(200, content=b"<html><body></body></html>"))
    with pytest.raises(PermanentError, match="No article text"):
        source.extract(_url_item())


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_private_addresses_are_blocked(address):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200)))
    source = UrlSource(client=client, resolve=lambda host: [address])
    with pytest.raises(PermanentError, match="private"):
        source.extract(_url_item())


def test_redirect_to_private_address_is_blocked():
    def handler(req):
        return httpx.Response(302, headers={"location": "http://internal.example/admin"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = UrlSource(
        client=client,
        resolve=lambda host: ["10.1.2.3"] if host == "internal.example" else ["93.184.216.34"],
    )
    with pytest.raises(PermanentError, match="private"):
        source.extract(_url_item())


def test_site_name_is_stripped_from_titles():
    from app.sources.url import _strip_site_name

    assert _strip_site_name("B-tree - Wikipedia", "Wikipedia") == "B-tree"
    assert _strip_site_name("Notes | Example Blog", "Example Blog") == "Notes"
    assert _strip_site_name("Wikipedia", "Wikipedia") == "Wikipedia"
    assert _strip_site_name("Plain title", None) == "Plain title"
    assert (
        _strip_site_name("B-tree - Wikipedia", "en.wikipedia.org", "en.wikipedia.org") == "B-tree"
    )
    assert _strip_site_name("Rust - Rust", None, "example.com") == "Rust - Rust"


def test_article_lines_lose_table_rules_and_footnote_markers():
    from app.sources.url import _tidy

    assert _tidy("| |---|---| |") == ""
    assert _tidy("| Type | | | Tree |") == "Type | Tree"
    assert _tidy("Invented in 1970[1] by Bayer[edit]") == "Invented in 1970 by Bayer"
    assert _tidy("Keeps [citation needed] keys sorted.") == "Keeps  keys sorted."
