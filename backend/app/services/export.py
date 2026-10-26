"""Export a library as a zip: Markdown to read, JSON to re-import or process, and optionally
the original uploads. Everything a person put in or Recall made for them, minus embeddings."""

import io
import json
import re
import zipfile
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Card, Chat, Item, SourceType, User
from app.services import files


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", slug)[:60].strip("-") or fallback


def item_markdown(item: Item, cards: list[Card]) -> str:
    lines = [f"# {item.title}", ""]
    source = "Note" if item.source_type == SourceType.note else item.source
    if item.source_type in (SourceType.pdf, SourceType.file):
        source = f"Uploaded file ({files.suffix(item.source).lstrip('.') or 'file'})"
    lines += [f"- Source: {source}", f"- Saved: {item.created_at:%Y-%m-%d}"]
    if item.tags:
        lines.append("- Tags: " + ", ".join(f"#{t.name}" for t in item.tags))
    if item.starred:
        lines.append("- Starred")
    if item.archived:
        lines.append("- Archived")
    lines.append("")
    if item.summary:
        lines += ["## Summary", "", item.summary, ""]
    details = item.details or {}
    if details.get("overview"):
        lines += ["## Overview", "", details["overview"], ""]
    if details.get("key_points"):
        lines += ["## Key points", ""] + [f"- {p}" for p in details["key_points"]] + [""]
    if details.get("sections"):
        lines += ["## Section by section", ""]
        for section in details["sections"]:
            lines += [f"### {section['heading']}", "", section["body"], ""]
    if item.note:
        lines += ["## My notes", "", item.note, ""]
    if item.highlights:
        lines += ["## Highlights", ""]
        for h in item.highlights:
            lines.append(f"> {h.quote}")
            if h.note:
                lines += ["", h.note]
            lines.append("")
    if cards:
        lines += ["## Flashcards", ""]
        for card in cards:
            lines += [f"**Q:** {card.question}", "", f"**A:** {card.answer}", ""]
    if item.content and item.source_type == SourceType.note:
        lines += ["## Text", ""] + [p["text"] for p in item.content] + [""]
    return "\n".join(lines).rstrip() + "\n"


def build_export(session: Session, user: User, include_files: bool = False) -> bytes:
    items = list(
        session.scalars(
            select(Item)
            .where(Item.user_id == user.id)
            .options(selectinload(Item.tags), selectinload(Item.highlights))
            .order_by(Item.created_at)
        )
    )
    cards_by_item: dict[int, list[Card]] = {}
    for card in session.scalars(select(Card).where(Card.user_id == user.id).order_by(Card.id)):
        cards_by_item.setdefault(card.item_id, []).append(card)
    chats = list(
        session.scalars(
            select(Chat)
            .where(Chat.user_id == user.id)
            .options(selectinload(Chat.messages))
            .order_by(Chat.created_at)
        )
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        data: dict = {
            "exported_at": datetime.now(UTC).isoformat(),
            "account": {"email": user.email, "name": user.name},
            "items": [],
            "chats": [],
        }
        for n, item in enumerate(items, start=1):
            name = f"{n:03}-{_slug(item.title, f'item-{item.id}')}"
            cards = cards_by_item.get(item.id, [])
            zf.writestr(f"library/{name}.md", item_markdown(item, cards))
            if item.content:
                zf.writestr(f"text/{name}.txt", "\n\n".join(p["text"] for p in item.content))
            stored = None
            if include_files and item.source_type in (SourceType.pdf, SourceType.file):
                original = files.read(item.source)
                if original is not None:
                    stored = f"files/{name}{files.suffix(item.source)}"
                    zf.writestr(stored, original)
            data["items"].append(
                {
                    "title": item.title,
                    "source_type": item.source_type.value,
                    "source": item.source
                    if item.source_type in (SourceType.url, SourceType.youtube)
                    else None,
                    "file": stored,
                    "created_at": item.created_at.isoformat(),
                    "status": item.status.value,
                    "starred": item.starred,
                    "archived": item.archived,
                    "tags": [t.name for t in item.tags],
                    "summary": item.summary,
                    "details": item.details,
                    "note": item.note,
                    "content": item.content,
                    "highlights": [
                        {
                            "quote": h.quote,
                            "note": h.note,
                            "start_char": h.start_char,
                            "end_char": h.end_char,
                        }
                        for h in item.highlights
                    ],
                    "flashcards": [
                        {"question": c.question, "answer": c.answer, "due_at": c.due_at.isoformat()}
                        for c in cards
                    ],
                }
            )
        for chat in chats:
            data["chats"].append(
                {
                    "title": chat.title,
                    "created_at": chat.created_at.isoformat(),
                    "messages": [
                        {
                            "role": m.role,
                            "content": m.content,
                            "cited": m.cited,
                            "sources": m.sources,
                        }
                        for m in chat.messages
                    ],
                }
            )
            if chat.messages:
                transcript = [f"# {chat.title}", ""]
                for m in chat.messages:
                    transcript += [
                        f"**{'You' if m.role == 'user' else 'Recall'}:** {m.content}",
                        "",
                    ]
                zf.writestr(
                    f"chats/{_slug(chat.title, f'chat-{chat.id}')}-{chat.id}.md",
                    "\n".join(transcript),
                )
        zf.writestr("recall.json", json.dumps(data, indent=2, ensure_ascii=False, default=str))
        zf.writestr(
            "README.md",
            f"# Recall export for {user.email}\n\n"
            f"{len(items)} items and {len(chats)} chats, exported {datetime.now(UTC):%Y-%m-%d}.\n\n"
            "- `library/`: one Markdown file per item: summary, notes, highlights, flashcards\n"
            "- `text/`: the full text Recall read from each item\n"
            "- `chats/`: your conversations\n"
            "- `recall.json`: everything above as data\n"
            + ("- `files/`: your original uploads\n" if include_files else ""),
        )
    return buffer.getvalue()
