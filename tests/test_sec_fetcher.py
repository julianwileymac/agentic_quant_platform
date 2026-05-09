from __future__ import annotations

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.api.sec import SecFilingsFetcher


def test_sec_fetcher_streams_rows_from_metadata(monkeypatch) -> None:
    called: dict[str, object] = {}

    class _FakeSecFilingsAdapter:
        def fetch_metadata(
            self,
            *,
            cik_or_ticker,
            form=None,
            start=None,
            end=None,
            limit=50,
        ):
            called["cik_or_ticker"] = cik_or_ticker
            called["form"] = form
            called["limit"] = limit
            return {
                "filings": [
                    {
                        "cik": "0000320193",
                        "accession_no": "0000320193-24-000001",
                        "form": "10-K",
                        "filed_at": "2024-10-31",
                    }
                ]
            }

    import aqp.data.sources.sec.filings as sec_filings_module

    monkeypatch.setattr(sec_filings_module, "SecFilingsAdapter", _FakeSecFilingsAdapter)
    fetcher = SecFilingsFetcher(
        cik="0000320193",
        forms=["10-K"],
        limit=5,
        chunk_rows=100,
    )
    ctx = NodeContext(
        pipeline_id="test",
        run_id="run-1",
        node_name="source.sec_filings",
        node_index=0,
    )

    batches = list(fetcher.fetch(ctx))

    assert called == {
        "cik_or_ticker": "0000320193",
        "form": ["10-K"],
        "limit": 5,
    }
    assert batches
    assert batches[0].num_rows == 1
    assert "accession_no" in batches[0].schema.names
