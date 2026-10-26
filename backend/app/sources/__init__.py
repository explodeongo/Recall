"""Source types: how each kind of saved item turns into text (NFR-5).

Adding a new source type (video, audio) means one new class implementing `Source`, an entry in
`get_source`, and a new `SourceType` enum value (plus its migration). The pipeline, search
and API don't change.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from app.models import Item, SourceType

if TYPE_CHECKING:
    from app.services.images import ExtractedImage


@dataclass(frozen=True)
class PageText:
    """Text from one page of a document. `page` is 1-based, or None for sources with no pages.

    Paragraphs are separated by a blank line.
    """

    page: int | None
    text: str


@dataclass(frozen=True)
class ExtractedDoc:
    title: str | None
    pages: list[PageText]
    # A cover and figures, where the source has them (services/images.py places them).
    images: list["ExtractedImage"] = field(default_factory=list)


class Source(Protocol):
    def extract(self, item: Item) -> ExtractedDoc: ...


def get_source(source_type: SourceType) -> Source:
    from app.sources.files import FileSource
    from app.sources.note import NoteSource
    from app.sources.pdf import PdfSource
    from app.sources.url import UrlSource
    from app.sources.youtube import YoutubeSource

    registry: dict[SourceType, type] = {
        SourceType.pdf: PdfSource,
        SourceType.url: UrlSource,
        SourceType.note: NoteSource,
        SourceType.file: FileSource,
        SourceType.youtube: YoutubeSource,
    }
    return registry[source_type]()
