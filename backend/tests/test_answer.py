def test_suggested_follow_ups_are_taken_off_the_answer():
    from app.services.answer import _Stream

    stream = _Stream()
    shown = ""
    for piece in [
        "B-trees keep keys sorted [1].",
        "\nNEXT: Why sorted? | ",
        "How do hash indexes differ | x",
    ]:
        shown += stream.feed(piece)
    shown += stream.rest()
    text, more, not_found = stream.finish()
    assert shown == text == "B-trees keep keys sorted [1]."
    assert stream.suggestions == ["Why sorted?", "How do hash indexes differ?"]  # "x" is too short
    assert more is None and not not_found

    # Next to a MORE: line, in either order.
    stream = _Stream()
    stream.feed("Part one [1].\nNEXT: A question? | Another one?\nMORE: the rest")
    assert stream.finish() == ("Part one [1].", "the rest", False)
    assert stream.suggestions == ["A question?", "Another one?"]
