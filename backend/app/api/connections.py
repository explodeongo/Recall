from fastapi import APIRouter, HTTPException

from app.deps import CurrentUser, SessionDep
from app.models import Item
from app.schemas import ConnectionOut, GraphOut, LinkOut
from app.services import connections as service
from app.services import links
from app.services.tags import color_of

router = APIRouter(tags=["connections"])


@router.get("/items/{item_id}/connections", response_model=list[ConnectionOut])
def item_connections(item_id: int, session: SessionDep, user: CurrentUser) -> list[dict]:
    """Saved items on a related topic, each with the passage in it closest to this item."""
    item = session.get(Item, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Item not found")
    return [
        {
            "item": c.item,
            "similarity": round(c.similarity, 3),
            "shared_tags": c.shared_tags,
            "passage": c.passage,
        }
        for c in service.connections(session, item)
    ]


@router.get("/items/{item_id}/links", response_model=list[LinkOut])
def item_links(item_id: int, session: SessionDep, user: CurrentUser) -> list[links.Link]:
    """Linked ideas: terms in this item's text that other saved items are about, each with
    those items and the passage in them that mentions it. No model call."""
    item = session.get(Item, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Item not found")
    return links.links_for(session, item)


@router.get("/graph", response_model=GraphOut)
def library_graph(session: SessionDep, user: CurrentUser) -> dict:
    """The library as a graph: items, and links between items on related topics."""
    items, edges = service.graph(session, user.id)
    groups = service.clusters(items, edges)
    cluster_of = {i: c.id for c in groups for i in c.item_ids}
    colors = {t.name: color_of(t) for i in items for t in i.tags}
    return {
        "clusters": [
            {
                "id": c.id,
                "label": c.label,
                "size": len(c.item_ids),
                "color": colors.get(c.label) if c.label else None,
            }
            for c in groups
        ],
        "nodes": [
            {
                "id": i.id,
                "title": i.title,
                "source_type": i.source_type,
                "tags": [{"id": t.id, "name": t.name, "color": color_of(t)} for t in i.tags],
                "created_at": i.created_at,
                "cluster": cluster_of.get(i.id),
            }
            for i in items
        ],
        "edges": [{"source": a, "target": b, "similarity": s} for a, b, s in edges],
    }
