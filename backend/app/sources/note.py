from app.models import Item
from app.services.images import note_images
from app.sources import ExtractedDoc, PageText
from app.sources.files import paragraphs_from_plain_text


class NoteSource:
    """Text typed or pasted into Recall. It's stored on the item itself; pictures added to it
    are referred to as ![what it shows](image:ID) and shown where they were added."""

    def extract(self, item: Item) -> ExtractedDoc:
        text, images = note_images(item.source)
        return ExtractedDoc(
            title=None,
            pages=[PageText(None, "\n\n".join(paragraphs_from_plain_text(text)))],
            images=images,
        )
