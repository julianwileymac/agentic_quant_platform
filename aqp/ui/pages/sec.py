"""SEC EDGAR Explorer — filings list + parsed financials preview."""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import get, post


@solara.component
def Page() -> None:
    cik_or_ticker = solara.use_reactive("AAPL")
    form = solara.use_reactive("")
    filings: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    financials: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    insider: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    ingest_task = solara.use_reactive("")
    error = solara.use_reactive("")

    def list_filings() -> None:
        if not cik_or_ticker.value.strip():
            return
        try:
            params: dict[str, Any] = {"limit": 25}
            if form.value.strip():
                params["form"] = form.value.strip()
            payload = get(
                f"/sec/company/{cik_or_ticker.value.strip()}/filings",
                params=params,
            )
            filings.set(list(payload.get("filings") or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            filings.set([])
            error.set(str(exc))

    def load_financials() -> None:
        try:
            payload = get(
                f"/sec/company/{cik_or_ticker.value.strip()}/financials",
                params={"limit": 500},
            )
            financials.set(list(payload.get("rows") or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            financials.set([])
            error.set(str(exc))

    def load_insider() -> None:
        try:
            payload = get(
                f"/sec/company/{cik_or_ticker.value.strip()}/insider",
                params={"limit": 200},
            )
            insider.set(list(payload.get("transactions") or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            insider.set([])
            error.set(str(exc))

    def ingest_all() -> None:
        try:
            body: dict[str, Any] = {
                "cik_or_ticker": cik_or_ticker.value.strip(),
                "artifacts": ["financials", "insider"],
            }
            if form.value.strip():
                body["form"] = form.value.strip()
            r = post("/sec/ingest", json=body)
            ingest_task.set(str(r.get("task_id", "")))
        except Exception as exc:  # pragma: no cover
            error.set(str(exc))

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1200px"}):
        solara.Markdown("# SEC EDGAR Explorer")
        solara.Markdown(
            "List filings, parsed financial statements, and insider "
            "transactions via the `edgartools` library. Requires "
            "`AQP_SEC_EDGAR_IDENTITY` and the `[sec]` extra."
        )
        with solara.Row():
            solara.InputText(label="CIK or ticker", value=cik_or_ticker)
            solara.InputText(label="Form filter (optional)", value=form)
            solara.Button("List filings", on_click=list_filings, color="primary")
            solara.Button("Financials", on_click=load_financials)
            solara.Button("Insider (Form 4)", on_click=load_insider)
            solara.Button("Ingest all", on_click=ingest_all)
        if error.value:
            solara.Error(error.value)
        if ingest_task.value:
            solara.Info(f"Ingest task queued: {ingest_task.value}")

        if filings.value:
            solara.Markdown("## Filings")
            solara.DataFrame(pd.DataFrame(filings.value))
        if financials.value:
            solara.Markdown("## Standardized Financials")
            solara.DataFrame(pd.DataFrame(financials.value))
        if insider.value:
            solara.Markdown("## Insider Transactions")
            solara.DataFrame(pd.DataFrame(insider.value))
