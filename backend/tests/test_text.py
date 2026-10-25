from app.services.text import chunk_pages, clean_pages, count_tokens
from app.sources import PageText


def _words(n: int, word: str = "alpha") -> str:
    return " ".join(f"{word}{i}" for i in range(n))


def test_cleaning_removes_running_headers_and_page_numbers():
    topics = ["Hashing.", "B-trees.", "Joins.", "Sorting."]
    pages = [
        PageText(i, f"Lecture notes - CS 501 - week {i}\n\n{topic}\n\nPage {i} of 4")
        for i, topic in enumerate(topics, start=1)
    ]
    assert [p.text for p in clean_pages(pages)] == topics


def test_cleaning_keeps_headers_when_too_few_pages_to_tell():
    pages = [PageText(1, "Title\n\nBody one."), PageText(2, "Title\n\nBody two.")]
    assert "Title" in clean_pages(pages)[0].text


def test_cleaning_repairs_hyphenation_and_line_wraps():
    [page] = clean_pages([PageText(1, "Indexes speed up re-\ntrieval of rows\nfrom   tables.")])
    assert page.text == "Indexes speed up retrieval of rows from tables."


def test_short_text_is_one_chunk_with_its_page():
    chunks = chunk_pages([PageText(3, "One short paragraph.")])
    assert [(c.text, c.page) for c in chunks] == [("One short paragraph.", 3)]


def test_empty_input_has_no_chunks():
    assert chunk_pages([PageText(1, "")]) == []


def test_chunks_respect_size_and_overlap():
    sentences = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_pages([PageText(None, sentences)], size=100, overlap=20)
    assert len(chunks) > 5
    assert all(count_tokens(c.text) <= 100 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        first_sentence = nxt.text.split(". ")[0]
        assert first_sentence in prev.text  # each chunk opens with the end of the previous one
    # nothing lost: every sentence appears in some chunk
    joined = " ".join(c.text for c in chunks)
    assert all(f"Sentence number {i} is here." in joined for i in range(200))


def test_paragraph_breaks_are_kept_inside_chunks():
    chunks = chunk_pages([PageText(1, "First paragraph.\n\nSecond paragraph.")])
    assert chunks[0].text == "First paragraph.\n\nSecond paragraph."


def test_a_single_huge_sentence_is_split_into_windows():
    chunks = chunk_pages([PageText(1, _words(1000))], size=100, overlap=10)
    assert all(count_tokens(c.text) <= 100 for c in chunks)
    assert "alpha999" in chunks[-1].text


def test_chunk_page_follows_where_new_text_starts():
    pages = [PageText(p, " ".join(f"Page {p} sentence {i}." for i in range(30))) for p in (1, 2)]
    chunks = chunk_pages(pages, size=60, overlap=10)
    assert chunks[0].page == 1
    assert chunks[-1].page == 2
    assert {c.page for c in chunks} == {1, 2}
