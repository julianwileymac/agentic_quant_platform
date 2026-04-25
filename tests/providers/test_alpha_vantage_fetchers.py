from __future__ import annotations


def test_alpha_vantage_fetchers_register_domains() -> None:
    import aqp.providers  # noqa: F401 - importing registers provider fetchers
    from aqp.providers.catalog import pick_fetcher

    quote = pick_fetcher("equity.quote", vendor="alpha_vantage")
    bars = pick_fetcher("equity.historical", vendor="alpha_vantage")
    balance = pick_fetcher("fundamentals.balance_sheet", vendor="alpha_vantage")

    assert quote is not None
    assert bars is not None
    assert balance is not None
    assert quote.describe()["vendor_key"] == "alpha_vantage"


def test_alpha_vantage_quote_transform() -> None:
    from aqp.providers.alpha_vantage import AlphaVantageEquityQuoteFetcher

    query = AlphaVantageEquityQuoteFetcher.transform_query({"symbol": "ibm"})
    rows = AlphaVantageEquityQuoteFetcher.transform_data(
        query,
        {
            "symbol": "IBM",
            "price": "187.2",
            "open": "184",
            "high": "188",
            "low": "183",
            "volume": "12345",
        },
    )

    assert rows[0].symbol == "IBM"
    assert rows[0].last_price == 187.2
