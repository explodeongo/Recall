def test_results_run_together_by_the_engine_are_separated():
    from app.services.web import WebResult, unglue

    glued = [
        WebResult(
            "Ann Lee - Data Scientist | LinkedInAnn Lee (@ann) • InstagramAnn Lee - Facebook",
            "https://a",
            "Builds data products. Photos and videos. Ann is on Facebook.",
        ),
        WebResult(
            "Ann Lee (@ann) • InstagramAnn Lee - Facebook",
            "https://b",
            "Photos and videos. Ann is on Facebook.",
        ),
        WebResult("Ann Lee - Facebook", "https://c", "Ann is on Facebook."),
    ]
    fixed = unglue(glued)
    assert [r.title for r in fixed] == [
        "Ann Lee - Data Scientist | LinkedIn",
        "Ann Lee (@ann) • Instagram",
        "Ann Lee - Facebook",
    ]
    assert [r.snippet for r in fixed] == [
        "Builds data products.",
        "Photos and videos.",
        "Ann is on Facebook.",
    ]


def test_web_passages_keep_the_ones_about_the_question():
    from app.services.web import web_passages
    from tests.helpers import FakeSearcher

    filler = "Subscribe to our newsletter for weekly tips, offers and news from the team. " * 6
    cake = (
        "To craft a cake, put three buckets of milk in the top row, sugar, an egg and sugar "
        "in the middle row, and three wheat in the bottom row of the crafting grid. "
    ) * 3
    page = "\n\n".join([filler] * 5 + [cake] + [filler] * 2)
    searcher = FakeSearcher([("Cake", "https://wiki/cake", "A food block.")])

    passages = web_passages("how to craft a cake", searcher, read_page=lambda result: page)

    assert passages and all(p.kind == "web" for p in passages)
    # Deep in the page, but it wins over the filler at the top.
    assert "crafting grid" in passages[0].text
    assert len(passages) <= 2  # at most two from any one page


def test_web_passages_fall_back_to_snippets_and_spread_over_pages():
    from app.services.web import web_passages
    from tests.helpers import FakeSearcher

    searcher = FakeSearcher(
        [
            ("Wolves", "https://a", "Tame a wolf by giving it bones until hearts appear."),
            ("Dogs", "https://b", "Tamed wolves become dogs that follow you."),
            ("Bones", "https://c", "Skeletons drop bones."),
        ]
    )

    passages = web_passages("how to tame a wolf", searcher, read_page=lambda result: "")

    assert [p.source for p in passages][0] == "https://a"
    assert {p.source for p in passages} == {"https://a", "https://b", "https://c"}


def test_web_passages_with_no_results():
    from app.services.web import web_passages
    from tests.helpers import FakeSearcher

    assert web_passages("anything", FakeSearcher([])) == []
