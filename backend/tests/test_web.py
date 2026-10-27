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
