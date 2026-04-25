"""Quick Chroma semantic search demo."""
from aqp.data.chroma_store import ChromaStore

store = ChromaStore()
for query in ("Apple stock daily bars", "e-commerce giant AMZN", "risk-free benchmark SPY"):
    print(f"\n>>> {query}")
    for h in store.search_datasets(query, k=2):
        m = h.get("metadata", {})
        print(f'  - {m.get("vt_symbol")}  rows={m.get("rows")}  dist={h.get("distance"):.3f}')
        print(f'    {m.get("path")}')
