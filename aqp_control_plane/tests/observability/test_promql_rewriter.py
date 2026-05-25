"""Unit tests for the identity-aware PromQL rewriter."""
from __future__ import annotations

import pytest

from aqp_cp.services.prometheus import (
    PromQLDeniedError,
    PromQLLabelInjector,
)


@pytest.fixture
def injector() -> PromQLLabelInjector:
    return PromQLLabelInjector(
        tenant_label="aqp_tenant",
        deny_patterns=("up", "prometheus_*", "kube_node_*", "process_*"),
    )


class TestPromQLLabelInjector:
    def test_bare_metric_gets_matcher(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite("cpu_usage", tenant_id="acme")
        assert result.rewritten == 'cpu_usage{aqp_tenant="acme"}'
        assert result.metrics_seen == ("cpu_usage",)
        assert result.metrics_denied == ()

    def test_metric_with_existing_labels_keeps_them(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite('cpu_usage{pod="foo"}', tenant_id="acme")
        assert result.rewritten == 'cpu_usage{aqp_tenant="acme", pod="foo"}'

    def test_metric_with_existing_tenant_label_left_alone(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite(
            'cpu_usage{aqp_tenant="other"}', tenant_id="acme"
        )
        assert result.rewritten == 'cpu_usage{aqp_tenant="other"}'

    def test_function_calls_unchanged(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite("rate(cpu_usage[5m])", tenant_id="acme")
        assert result.rewritten == 'rate(cpu_usage{aqp_tenant="acme"}[5m])'

    def test_binary_op_both_sides_rewritten(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite(
            "sum(rate(cpu_usage[5m])) / count(memory_usage)",
            tenant_id="acme",
        )
        assert 'cpu_usage{aqp_tenant="acme"}' in result.rewritten
        assert 'memory_usage{aqp_tenant="acme"}' in result.rewritten

    def test_regex_label_preserved(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite(
            'cpu_usage{pod=~"foo.*"}', tenant_id="acme"
        )
        assert result.rewritten == 'cpu_usage{aqp_tenant="acme", pod=~"foo.*"}'

    def test_aggregation_modifier_keywords_not_rewritten(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite(
            "sum(cpu_usage) by (pod)", tenant_id="acme"
        )
        assert "by(" not in result.rewritten and "by (" in result.rewritten
        assert 'cpu_usage{aqp_tenant="acme"}' in result.rewritten

    def test_deny_listed_metric_raises(self, injector: PromQLLabelInjector) -> None:
        with pytest.raises(PromQLDeniedError) as exc_info:
            injector.rewrite("up", tenant_id="acme")
        assert "up" in exc_info.value.metrics

    def test_deny_pattern_wildcard_match(
        self, injector: PromQLLabelInjector
    ) -> None:
        with pytest.raises(PromQLDeniedError) as exc_info:
            injector.rewrite("kube_node_status_condition", tenant_id="acme")
        assert "kube_node_status_condition" in exc_info.value.metrics

    def test_empty_query_passes_through(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite("", tenant_id="acme")
        assert result.rewritten == ""

    def test_tenant_id_double_quote_escaped(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite('cpu_usage', tenant_id='ac"me')
        assert result.rewritten == 'cpu_usage{aqp_tenant="ac\\"me"}'

    def test_subquery_rewritten(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite("rate(cpu_usage[5m:1m])", tenant_id="acme")
        assert 'cpu_usage{aqp_tenant="acme"}' in result.rewritten

    def test_offset_keyword_skipped(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite(
            "cpu_usage offset 5m", tenant_id="acme"
        )
        # The metric should be wrapped; "offset" should not be wrapped.
        assert 'cpu_usage{aqp_tenant="acme"}' in result.rewritten
        assert 'offset{' not in result.rewritten

    def test_empty_label_block(self, injector: PromQLLabelInjector) -> None:
        result = injector.rewrite("cpu_usage{}", tenant_id="acme")
        assert result.rewritten == 'cpu_usage{aqp_tenant="acme"}'

    def test_metrics_seen_excludes_functions(
        self, injector: PromQLLabelInjector
    ) -> None:
        result = injector.rewrite(
            "sum(rate(cpu_usage[5m]))", tenant_id="acme"
        )
        assert result.metrics_seen == ("cpu_usage",)
