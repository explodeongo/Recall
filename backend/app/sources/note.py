from app.models import Item
from app.sources import ExtractedDoc, PageText
from app.sources.files import paragraphs_from_plain_text


class NoteSource:
    """Text typed or pasted into Recall. It's stored on the item itself."""

    def extract(self, item: Item) -> ExtractedDoc:
        return ExtractedDoc(
            title=None,
            pages=[PageText(None, "\n\n".join(paragraphs_from_plain_text(item.source)))],
        )
