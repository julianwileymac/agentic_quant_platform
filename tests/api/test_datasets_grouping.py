from __future__ import annotations

from aqp.api.routes.datasets import _base_group_name, _heuristic_grouping


def test_base_group_name_strips_common_split_suffixes() -> None:
    assert _base_group_name("cfpb_part_001") == "cfpb"
    assert _base_group_name("sec-filings-chunk12") == "sec-filings"
    assert _base_group_name("uspto_0001of0010") == "uspto"
    assert _base_group_name("fda_batch_07") == "fda"


def test_heuristic_grouping_returns_namespace_groups() -> None:
    groups = _heuristic_grouping(
        [
            "aqp_ingest.cfpb_part_001",
            "aqp_ingest.cfpb_part_002",
            "aqp_ingest.cfpb_part_003",
            "aqp_ingest.sec_master",
        ],
        min_group_size=2,
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.group_name == "aqp_ingest.cfpb"
    assert sorted(group.members) == [
        "aqp_ingest.cfpb_part_001",
        "aqp_ingest.cfpb_part_002",
        "aqp_ingest.cfpb_part_003",
    ]
