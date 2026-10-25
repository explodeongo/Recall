# Evaluation corpus

Twenty English Wikipedia articles, each pinned to a revision (see `../corpus.json` for the
exact revision links and retrieval dates). The text was fetched with Recall's own article reader
(`python -m eval.fetch_corpus`) and cleaned the same way the app cleans saved links.

The articles are by Wikipedia contributors and are licensed under the
[Creative Commons Attribution-ShareAlike 4.0 License](https://creativecommons.org/licenses/by-sa/4.0/).
These snapshots are redistributed under the same license. Recall's own code is not affected.

| Cluster | Articles |
| --- | --- |
| Databases and data structures | B-tree, Hash table, Database index, Log-structured merge-tree, Bloom filter |
| Distributed systems | Raft, Paxos, CAP theorem, Consistent hashing, Two-phase commit protocol |
| Machine learning | Transformer, Attention, Word2Vec, BERT, Retrieval-augmented generation |
| Networking and systems | TCP congestion control, HTTP/2, Garbage collection, Dijkstra's algorithm, Public-key cryptography |

The clusters overlap on purpose: several articles discuss hashing, trees, consensus or attention,
so finding the right passage takes more than matching the topic.
