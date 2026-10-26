"""Tag colors and the operations of the tag manager."""

import colorsys
import hashlib
import re

from sqlalchemy import ColumnElement, and_, delete, func, select, true, update
from sqlalchemy.orm import Session

from app.models import Item, Tag, item_tags

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_color(name: str) -> str:
    """A stable, pleasant color for a tag that hasn't been given one: the hue comes from the
    name, saturation and lightness are fixed so every default sits well together."""
    hue = int(hashlib.sha1(name.encode()).hexdigest()[:4], 16) / 0xFFFF
    r, g, b = colorsys.hls_to_rgb(hue, 0.58, 0.62)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def color_of(tag: Tag) -> str:
    return (tag.color or default_color(tag.name)).lower()


def usage(session: Session, user_id: int) -> list[tuple[Tag, int]]:
    """The person's tags with how many items use each; empty ones only if they made them."""
    count = func.count(item_tags.c.item_id)
    rows = session.execute(
        select(Tag, count.label("n"))
        .outerjoin(item_tags, item_tags.c.tag_id == Tag.id)
        .where(Tag.user_id == user_id)
        .group_by(Tag.id)
        .order_by(count.desc(), Tag.name)
    ).all()
    return [(tag, n) for tag, n in rows if n > 0 or tag.user_made]


def merge(session: Session, source: Tag, target: Tag) -> None:
    """Move every item from `source` to `target`, then remove `source`."""
    already = select(item_tags.c.item_id).where(item_tags.c.tag_id == target.id)
    session.execute(
        update(item_tags)
        .where(item_tags.c.tag_id == source.id, item_tags.c.item_id.not_in(already))
        .values(tag_id=target.id)
    )
    session.execute(delete(item_tags).where(item_tags.c.tag_id == source.id))
    session.delete(source)


def has_tags(names: list[str], match: str = "all") -> ColumnElement[bool]:
    """Items carrying every one of `names` ("all") or at least one ("any"). Plain SQL; no
    LLM is involved in filtering (NFR-2)."""
    names = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not names:
        return true()
    if match == "any":
        return Item.tags.any(Tag.name.in_(names))
    return and_(*(Item.tags.any(Tag.name == n) for n in names))


def parse_tags(tags: str | None, tag: str | None = None) -> list[str]:
    """`?tags=a,b` (and the older single `?tag=a`) as a list of names."""
    raw = (tags or "").split(",") + ([tag] if tag else [])
    return list(dict.fromkeys(n.strip().lower() for n in raw if n and n.strip()))
