"""Snapshot the evaluation corpus: python -m eval.fetch_corpus [doc ids...]

Each Wikipedia article is pinned to a revision, fetched through the app's own UrlSource (so the
evaluation reads text exactly as Recall would), cleaned, and saved to eval/corpus/<id>.txt.
The snapshots are committed, so the evaluation never depends on the network.
"""

import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx

from app.models import Item, SourceType
from app.services.text import clean_pages
from app.sources.url import UrlSource, user_agent

HERE = Path(__file__).parent
API = "https://en.wikipedia.org/w/api.php"

# id -> Wikipedia title. Four clusters of five, chosen to overlap so retrieval has to work.
ARTICLES = {
    # databases and data structures
    "btree": "B-tree",
    "hash-table": "Hash table",
    "database-index": "Database index",
    "lsm-tree": "Log-structured merge-tree",
    "bloom-filter": "Bloom filter",
    # distributed systems
    "raft": "Raft (algorithm)",
    "paxos": "Paxos (computer science)",
    "cap-theorem": "CAP theorem",
    "consistent-hashing": "Consistent hashing",
    "two-phase-commit": "Two-phase commit protocol",
    # machine learning
    "transformer": "Transformer (deep learning)",
    "attention": "Attention (machine learning)",
    "word2vec": "Word2vec",
    "bert": "BERT (language model)",
    "rag": "Retrieval-augmented generation",
    # networking and systems
    "tcp-congestion": "TCP congestion control",
    "http2": "HTTP/2",
    "garbage-collection": "Garbage collection (computer science)",
    "dijkstra": "Dijkstra's algorithm",
    "public-key-crypto": "Public-key cryptography",
}


def latest_revision(client: httpx.Client, title: str) -> tuple[str, int]:
    resp = client.get(
        API,
        params={
            "action": "query",
            "prop": "revisions",
            "rvprop": "ids",
            "titles": title,
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        },
    )
    resp.raise_for_status()
    page = resp.json()["query"]["pages"][0]
    return page["title"], page["revisions"][0]["revid"]


def main() -> None:
    only = set(sys.argv[1:])
    client = httpx.Client(timeout=30, headers={"User-Agent": user_agent()})
    source = UrlSource()
    manifest_path = HERE / "corpus.json"
    manifest = (
        {d["id"]: d for d in json.loads(manifest_path.read_text())}
        if manifest_path.exists()
        else {}
    )

    for doc_id, title in ARTICLES.items():
        if only and doc_id not in only:
            continue
        canonical, revid = latest_revision(client, title)
        slug = quote(canonical.replace(" ", "_"))
        url = f"https://en.wikipedia.org/w/index.php?title={slug}&oldid={revid}"
        doc = source.extract(Item(title=canonical, source_type=SourceType.url, source=url))
        text = "\n\n".join(p.text for p in clean_pages(doc.pages) if p.text)
        (HERE / "corpus" / f"{doc_id}.txt").write_text(text + "\n")
        manifest[doc_id] = {
            "id": doc_id,
            "title": canonical,
            "url": f"https://en.wikipedia.org/wiki/{slug}",
            "revision_url": url,
            "license": "CC BY-SA 4.0",
            "retrieved": date.today().isoformat(),
            "chars": len(text),
        }
        print(f"{doc_id:20} {len(text):>7} chars  {canonical} @ {revid}")

    ordered = [manifest[k] for k in ARTICLES if k in manifest]
    manifest_path.write_text(json.dumps(ordered, indent=2) + "\n")


if __name__ == "__main__":
    main()
