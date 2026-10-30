"""Guest accounts for the public demo.

"Try the demo" gives a visitor a private copy of the demo library: the account named by
GUEST_TEMPLATE_EMAIL, with its items (text, passages and their vectors), tags, notes,
highlights, pictures, chats and flashcards. The copy is made inside the database with no LLM
calls, in well under a second, so visitors can save, delete and ask freely and nobody sees
anyone else's questions. Dates move with it, so the library always looks a few weeks old.

Files (PDFs, web pages' PDFs and pictures) aren't copied: the copies point at the template's, which
files.delete never removes. Guests older than GUEST_HOURS are deleted when the next one
arrives, so a free host needs no scheduled job.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import Table, delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Card,
    Chat,
    ChatMessage,
    Item,
    ItemImage,
    Review,
    SourceType,
    Tag,
    User,
)
from app.services.images import IMAGE_TOKEN


class NoTemplate(LookupError):
    """GUEST_TEMPLATE_EMAIL isn't set, or no account has it."""


def template_user(session: Session) -> User | None:
    email = get_settings().guest_template_email
    if not email:
        return None
    return session.scalars(select(User).where(User.email == email.strip().lower())).first()


def create_guest(session: Session) -> User:
    template = template_user(session)
    if template is None:
        raise NoTemplate
    user = User(
        email=f"guest-{secrets.token_hex(8)}@guest.invalid",
        name="Guest",
        password_hash="!",  # matches no password, so a guest can only come in through the cookie
        is_guest=True,
    )
    session.add(user)
    session.flush()
    _copy_library(session, template.id, user.id)
    return user


def remove_expired(session: Session) -> list[str]:
    """Delete guests past GUEST_HOURS, and the oldest beyond MAX_GUESTS - 1 to make room for a
    new one. Returns their files' keys, to delete once committed."""
    settings = get_settings()
    guests = select(User.id).where(User.is_guest)
    expired = guests.where(
        User.created_at < datetime.now(UTC) - timedelta(hours=settings.guest_hours)
    )
    crowded = guests.order_by(User.created_at.desc()).offset(max(settings.max_guests - 1, 0))
    ids = set(session.scalars(expired)) | set(session.scalars(crowded))
    if not ids:
        return []
    keys = list(
        session.scalars(
            select(Item.source).where(
                Item.user_id.in_(ids), Item.source_type.in_([SourceType.pdf, SourceType.file])
            )
        )
    )
    keys += session.scalars(
        select(Item.pages_file).where(Item.user_id.in_(ids), Item.pages_file.is_not(None))
    )
    keys += session.scalars(select(ItemImage.key).where(ItemImage.user_id.in_(ids)))
    session.execute(delete(User).where(User.id.in_(ids)))  # everything else cascades
    return keys


def _rows(session: Session, table: Table, *where) -> list[dict]:
    return [
        dict(r)
        for r in session.execute(select(table).where(*where).order_by(table.c.id)).mappings()
    ]


def _insert(session: Session, table: Table, rows: list[dict]) -> list[int]:
    """Insert rows (without their ids) and return the new ids, in the same order."""
    if not rows:
        return []
    for row in rows:
        row.pop("id", None)
    stmt = insert(table).returning(table.c.id, sort_by_parameter_order=True)
    return list(session.scalars(stmt, rows))


def _pairs(mapping: dict[int, int]) -> dict:
    return {"old": list(mapping), "new": list(mapping.values())}


def _copy_library(session: Session, source: int, target: int) -> None:
    items_t, tags_t, images_t = Item.__table__, Tag.__table__, ItemImage.__table__
    cards_t, reviews_t = Card.__table__, Review.__table__
    chats_t, messages_t = Chat.__table__, ChatMessage.__table__

    # The newest activity lands a day ago: recent, but not "today", which daily limits count.
    latest = [
        select(func.max(Item.created_at)).where(Item.user_id == source),
        select(func.max(Item.last_opened_at)).where(Item.user_id == source),
        select(func.max(Chat.updated_at)).where(Chat.user_id == source),
        select(func.max(Card.created_at)).where(Card.user_id == source),
        select(func.max(Review.reviewed_at)).where(Review.user_id == source),
    ]
    newest = max((w for q in latest if (w := session.scalar(q))), default=datetime.now(UTC))
    shift = datetime.now(UTC) - timedelta(days=1) - newest

    def moved(when: datetime | None) -> datetime | None:
        return when + shift if when is not None else None

    tags = _rows(session, tags_t, tags_t.c.user_id == source)
    old_tags = [t["id"] for t in tags]
    for t in tags:
        t["user_id"] = target
    tag_map = dict(zip(old_tags, _insert(session, tags_t, tags), strict=True))

    items = _rows(session, items_t, items_t.c.user_id == source)
    old_items = [i["id"] for i in items]
    covers = {i["id"]: i["cover_image_id"] for i in items}
    notes = {i["id"]: i["note"] for i in items}
    for i in items:
        i |= {
            "user_id": target,
            "cover_image_id": None,
            "created_at": moved(i["created_at"]),
            "last_opened_at": moved(i["last_opened_at"]),
        }
    item_map = dict(zip(old_items, _insert(session, items_t, items), strict=True))

    pictures = [
        p
        for p in _rows(session, images_t, images_t.c.user_id == source)
        if p["item_id"] in item_map
    ]
    old_pictures = [p["id"] for p in pictures]
    for p in pictures:
        p |= {"user_id": target, "item_id": item_map[p["item_id"]]}
    image_map = dict(zip(old_pictures, _insert(session, images_t, pictures), strict=True))

    def new_image_tokens(note: str) -> str:
        def swap(m):
            old = int(m.group(2))
            return f"![{m.group(1)}](image:{image_map.get(old, old)})"

        return IMAGE_TOKEN.sub(swap, note)

    for old, new in item_map.items():
        values = {}
        if covers[old] in image_map:
            values["cover_image_id"] = image_map[covers[old]]
        if notes[old] and "image:" in notes[old]:
            values["note"] = new_image_tokens(notes[old])
        if values:
            session.execute(items_t.update().where(items_t.c.id == new).values(**values))

    # Passages are the bulk (text and vectors), so they're copied without leaving the database.
    ids = _pairs(item_map)
    mapped = "unnest(CAST(:old AS int[]), CAST(:new AS int[])) AS m(old_id, new_id)"
    session.execute(
        text(
            "INSERT INTO chunks (item_id, chunk_index, chunk_text, kind, page, start_char, "
            "end_char, embedding) SELECT m.new_id, c.chunk_index, c.chunk_text, c.kind, c.page, "
            f"c.start_char, c.end_char, c.embedding FROM chunks c JOIN {mapped} "
            "ON c.item_id = m.old_id"
        ),
        ids,
    )
    chunk_map = dict(
        session.execute(
            text(
                f"SELECT o.id, n.id FROM chunks o JOIN {mapped} ON o.item_id = m.old_id "
                "JOIN chunks n ON n.item_id = m.new_id AND n.chunk_index = o.chunk_index "
                "AND n.kind = o.kind"
            ),
            ids,
        ).all()
    )
    session.execute(
        text(
            f"INSERT INTO item_tags (item_id, tag_id) SELECT m.new_id, t.new_id FROM item_tags x "
            f"JOIN {mapped} ON x.item_id = m.old_id "
            "JOIN unnest(CAST(:old_tags AS int[]), CAST(:new_tags AS int[])) AS t(old_id, new_id) "
            "ON x.tag_id = t.old_id"
        ),
        ids | {"old_tags": list(tag_map), "new_tags": list(tag_map.values())},
    )
    session.execute(
        text(
            "INSERT INTO highlights (user_id, item_id, start_char, end_char, quote, note, "
            "created_at) SELECT :user, m.new_id, h.start_char, h.end_char, h.quote, h.note, "
            f"h.created_at + :shift FROM highlights h JOIN {mapped} ON h.item_id = m.old_id"
        ),
        ids | {"user": target, "shift": shift},
    )

    cards = [
        c for c in _rows(session, cards_t, cards_t.c.user_id == source) if c["item_id"] in item_map
    ]
    old_cards = [c["id"] for c in cards]
    for c in cards:
        c |= {
            "user_id": target,
            "item_id": item_map[c["item_id"]],
            "due_at": moved(c["due_at"]),
            "last_reviewed_at": moved(c["last_reviewed_at"]),
            "created_at": moved(c["created_at"]),
        }
    card_map = dict(zip(old_cards, _insert(session, cards_t, cards), strict=True))
    reviews = [
        r
        for r in _rows(session, reviews_t, reviews_t.c.user_id == source)
        if r["card_id"] in card_map
    ]
    for r in reviews:
        r |= {
            "user_id": target,
            "card_id": card_map[r["card_id"]],
            "reviewed_at": moved(r["reviewed_at"]),
        }
    _insert(session, reviews_t, reviews)

    chats = _rows(session, chats_t, chats_t.c.user_id == source)
    old_chats = [c["id"] for c in chats]
    for c in chats:
        c |= {
            "user_id": target,
            "item_id": item_map.get(c["item_id"]),
            "created_at": moved(c["created_at"]),
            "updated_at": moved(c["updated_at"]),
        }
    chat_map = dict(zip(old_chats, _insert(session, chats_t, chats), strict=True))
    messages = _rows(session, messages_t, messages_t.c.chat_id.in_(list(chat_map)))
    for m in messages:
        m |= {
            "chat_id": chat_map[m["chat_id"]],
            "sources": _remap_sources(m["sources"], item_map, chunk_map, image_map),
            "context": _remap_context(m["context"], item_map),
            "saved_item_id": item_map.get(m["saved_item_id"]),
            "created_at": moved(m["created_at"]),
        }
    _insert(session, messages_t, messages)


def _remap_sources(sources, item_map, chunk_map, image_map):
    if not sources:
        return sources
    out = []
    for s in sources:
        s = dict(s)
        if s.get("item_id") is not None:
            s["item_id"] = item_map.get(s["item_id"], s["item_id"])
        if s.get("chunk_id") is not None:
            s["chunk_id"] = chunk_map.get(s["chunk_id"], s["chunk_id"])
        if s.get("images"):
            s["images"] = [{**p, "id": image_map.get(p["id"], p["id"])} for p in s["images"]]
        out.append(s)
    return out


def _remap_context(context, item_map):
    if not context or not context.get("items"):
        return context
    items = [{**i, "id": item_map.get(i["id"], i["id"])} for i in context["items"]]
    return {**context, "items": items}
