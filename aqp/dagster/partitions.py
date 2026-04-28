"""Reusable Dagster partition definitions."""
from __future__ import annotations


def daily_partitions(*, start_date: str = "2020-01-01"):
    from dagster import DailyPartitionsDefinition

    return DailyPartitionsDefinition(start_date=start_date)


def weekly_partitions(*, start_date: str = "2020-01-01"):
    from dagster import WeeklyPartitionsDefinition

    return WeeklyPartitionsDefinition(start_date=start_date)


def monthly_partitions(*, start_date: str = "2020-01-01"):
    from dagster import MonthlyPartitionsDefinition

    return MonthlyPartitionsDefinition(start_date=start_date)


def symbol_partitions(symbols: list[str]):
    from dagster import StaticPartitionsDefinition

    return StaticPartitionsDefinition(list(symbols))


def regulatory_partitions():
    """Static partition over the four regulatory namespaces."""
    from dagster import StaticPartitionsDefinition

    return StaticPartitionsDefinition(
        ["aqp_cfpb", "aqp_fda", "aqp_uspto", "aqp_sec"]
    )


__all__ = [
    "daily_partitions",
    "monthly_partitions",
    "regulatory_partitions",
    "symbol_partitions",
    "weekly_partitions",
]
