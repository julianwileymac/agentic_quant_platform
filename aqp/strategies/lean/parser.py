"""AST-driven inspector for LEAN ``QCAlgorithm`` subclasses.

Extracts the metadata the ingester needs to register a template as a
Phase 1 :class:`aqp.persistence.models_resources.Resource` row:

- class name + base class
- docstring (used as the resource description)
- asset class detection (equities / options / futures / crypto / forex)
- indicator references (``self.MACD``, ``self.SMA``, ``self.OptionChainProvider``...)
- universe symbols (``self.AddEquity("SPY")`` etc.)
- categorisation tags (``machine_learning`` / ``options`` /
  ``multi_leg`` / ``momentum`` / ``mean_reversion`` / ``microstructure``)

Pure-Python; no LEAN runtime needed. Safe to run in CI / Celery.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Iterator


# Asset-class detection — maps the ``self.Add<XXX>`` API surface to a
# coarse asset_class tag. Order matters: most-specific first.
_ASSET_CLASS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("AddOption", "options"),
    ("AddIndexOption", "options"),
    ("AddFutureOption", "options"),
    ("OptionChain", "options"),
    ("AddFuture", "futures"),
    ("AddCrypto", "crypto"),
    ("AddForex", "forex"),
    ("AddCfd", "cfd"),
    ("AddIndex", "indices"),
    ("AddEquity", "equities"),
)


# Tag derivation — substring matches against the source. Multiple tags
# may apply per template.
_TAG_PATTERNS: tuple[tuple[str, str], ...] = (
    ("pytorch", "machine_learning"),
    ("tensorflow", "machine_learning"),
    ("sklearn", "machine_learning"),
    ("xgboost", "machine_learning"),
    ("neural", "machine_learning"),
    ("OptionStrategies", "multi_leg"),
    ("butterfly", "multi_leg"),
    ("iron_condor", "multi_leg"),
    ("Straddle", "multi_leg"),
    ("Strangle", "multi_leg"),
    ("MACD", "momentum"),
    ("RSI", "momentum"),
    ("BollingerBands", "mean_reversion"),
    ("EMA", "momentum"),
    ("PairsTrading", "mean_reversion"),
    ("OnFill", "microstructure"),
    ("OrderBook", "microstructure"),
    ("LimitOrder", "microstructure"),
    ("alpha", "alpha"),
    ("MeanReversion", "mean_reversion"),
    ("Momentum", "momentum"),
)


@dataclass
class LeanTemplateInfo:
    """Structured metadata extracted from one LEAN template file."""

    class_name: str
    base_class: str
    docstring: str
    asset_classes: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    universe_symbols: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_source: str = ""
    source_path: str | None = None

    def to_metadata_dict(self) -> dict[str, object]:
        return {
            "class_name": self.class_name,
            "base_class": self.base_class,
            "asset_classes": list(self.asset_classes),
            "indicators": list(self.indicators),
            "universe_symbols": list(self.universe_symbols),
            "tags": list(self.tags),
            "source_path": self.source_path,
            "framework": "lean",
        }


def _iter_attribute_chains(tree: ast.AST) -> Iterator[ast.Attribute]:
    """Yield every ``Attribute`` node in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            yield node


def _collect_indicator_calls(tree: ast.AST) -> list[str]:
    """Return the upper-cased self.<INDICATOR>(...) names referenced."""
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "self":
            continue
        name = func.attr
        # LEAN indicator naming convention: short upper-case or
        # PascalCase. Hand-pick the common ones to keep noise down.
        if name in {
            "MACD", "SMA", "EMA", "RSI", "BB", "BollingerBands",
            "ATR", "OBV", "ADX", "STD", "Stochastic", "OptionChainProvider",
            "FuturesChain", "OptionChain",
        }:
            seen.add(name)
    return sorted(seen)


def _collect_universe(tree: ast.AST) -> tuple[list[str], list[str]]:
    """Walk ``self.AddEquity('SPY')`` / ``AddCrypto('BTCUSD')`` etc.

    Returns ``(asset_classes, symbols)`` deduped and sorted.
    """
    classes: set[str] = set()
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        api = func.attr
        for pattern, cls in _ASSET_CLASS_PATTERNS:
            if api.startswith(pattern):
                classes.add(cls)
                break
        if api.startswith("Add"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    symbols.add(arg.value)
    return sorted(classes), sorted(symbols)


def _derive_tags(source: str) -> list[str]:
    """Substring-match the source against :data:`_TAG_PATTERNS`."""
    tags: set[str] = set()
    lower = source.lower()
    for needle, tag in _TAG_PATTERNS:
        if needle.lower() in lower:
            tags.add(tag)
    return sorted(tags)


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _slug_from_class(name: str) -> str:
    return _CAMEL_RE.sub("-", name).lower()


def parse_lean_source(
    source: str, *, source_path: str | None = None
) -> LeanTemplateInfo | None:
    """Inspect *source* and return :class:`LeanTemplateInfo` or ``None``.

    Returns ``None`` when the file doesn't contain a class that
    extends ``QCAlgorithm`` — the bulk of files under
    ``Algorithm.Python/`` follow that pattern but some are framework /
    examples / helpers.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    target_class: ast.ClassDef | None = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        # Filter on base class — QCAlgorithm is the LEAN entry point.
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)
        if any(b == "QCAlgorithm" for b in bases):
            target_class = node
            break

    if target_class is None:
        return None

    docstring = ast.get_docstring(target_class) or ""
    asset_classes, symbols = _collect_universe(target_class)
    indicators = _collect_indicator_calls(target_class)
    tags = _derive_tags(source)

    base_name = ""
    if target_class.bases:
        first = target_class.bases[0]
        if isinstance(first, ast.Name):
            base_name = first.id
        elif isinstance(first, ast.Attribute):
            base_name = first.attr

    return LeanTemplateInfo(
        class_name=target_class.name,
        base_class=base_name,
        docstring=docstring,
        asset_classes=asset_classes,
        indicators=indicators,
        universe_symbols=symbols,
        tags=tags,
        raw_source=source,
        source_path=source_path,
    )


__all__ = ["LeanTemplateInfo", "parse_lean_source"]
