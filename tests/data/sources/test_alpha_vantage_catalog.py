from __future__ import annotations


def test_lake_supported_functions_have_iceberg_metadata() -> None:
    from aqp.data.sources.alpha_vantage.catalog import lake_supported_functions

    entries = lake_supported_functions()
    assert entries, "expected at least one lake-supported endpoint"
    for entry in entries:
        assert entry.iceberg_table, f"{entry.id} missing iceberg_table"
        assert entry.iceberg_identifier == f"aqp_alpha_vantage.{entry.iceberg_table}"
        assert entry.partition_spec, f"{entry.id} missing partition_spec"


def test_function_to_dict_includes_partition_spec() -> None:
    from aqp.data.sources.alpha_vantage.catalog import get_function

    fn = get_function("timeseries.daily_adjusted")
    assert fn is not None
    payload = fn.to_dict()
    assert payload["iceberg_table"] == "time_series_daily_adjusted"
    assert payload["iceberg_identifier"] == "aqp_alpha_vantage.time_series_daily_adjusted"
    transforms = {field["transform"] for field in payload["partition_spec"]}
    assert "bucket[16]" in transforms
    assert "month" in transforms


def test_function_by_id_is_case_insensitive() -> None:
    from aqp.data.sources.alpha_vantage.catalog import function_by_id

    payload = function_by_id("TIME_SERIES_DAILY_ADJUSTED")
    assert payload is not None
    assert payload["id"] == "timeseries.daily_adjusted"
