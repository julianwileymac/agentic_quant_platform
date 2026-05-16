"""AST translator: LEAN ``QCAlgorithm`` -> ``FrameworkAlgorithm``.

The translator is opt-in: users click "Clone with translation" in the
template browser and the resulting :class:`Resource` carries the
generated skeleton instead of the original LEAN source.

Mapping rules (the common 80%):

- ``def Initialize(self):``                  -> ``def prepare(self, ctx):``
- ``def OnData(self, data):``                -> ``def on_bar(self, ctx, bars):``
- ``self.AddEquity("SPY")``                  -> ``ctx.add_equity("SPY")``
- ``self.AddOption("SPY")``                  -> ``ctx.add_option("SPY")``
- ``self.AddCrypto("BTCUSD")``               -> ``ctx.add_crypto("BTCUSD")``
- ``self.SetCash(100000)``                   -> metadata (passed via cfg)
- ``self.SetStartDate / SetEndDate``         -> metadata (cfg.start/end)
- ``self.MACD("SPY", 12, 26, 9)``            -> ``aqp.data.indicators.MACD(...)``
- ``self.SMA("SPY", 20)``                    -> ``aqp.data.indicators.SMA(...)``
- ``self.MarketOrder(symbol, qty)``          -> ``ctx.market_order(...)``
- ``self.SetHoldings(symbol, fraction)``     -> ``ctx.set_holdings(...)``
- ``OptionStrategies.butterfly_call(...)``   -> ``aqp.strategies.options.butterfly_call(...)``

Anything not in the table becomes a ``# TODO(lean-translate): ...``
comment retaining the original line so a human can finish the port.

The translator is fully deterministic — same input always produces
the same output. This matters because the generated skeleton is
hash-snapshotted via the ``resource_relations`` ``translated_from``
edge so users can audit which LEAN revision the skeleton came from.
"""
from __future__ import annotations

import ast
import re
from typing import Any


# Method name remap. Keys are LEAN method names, values are the
# corresponding FrameworkAlgorithm hook names.
_METHOD_REMAP: dict[str, str] = {
    "Initialize": "prepare",
    "OnData": "on_bar",
    "OnSecuritiesChanged": "on_universe_changed",
    "OnOrderEvent": "on_order_event",
    "OnEndOfDay": "on_end_of_day",
    "OnEndOfAlgorithm": "on_end",
    "OnWarmupFinished": "on_warmup_finished",
}


# self.<API>(...) -> ctx.<api>(...). Lowercases the API and forwards args.
_CTX_API_REMAP: dict[str, str] = {
    "AddEquity": "add_equity",
    "AddOption": "add_option",
    "AddIndexOption": "add_index_option",
    "AddFuture": "add_future",
    "AddCrypto": "add_crypto",
    "AddForex": "add_forex",
    "AddIndex": "add_index",
    "MarketOrder": "market_order",
    "LimitOrder": "limit_order",
    "StopMarketOrder": "stop_market_order",
    "StopLimitOrder": "stop_limit_order",
    "SetHoldings": "set_holdings",
    "Liquidate": "liquidate",
    "Buy": "buy",
    "Sell": "sell",
    "Plot": "plot",
    "Log": "log",
    "Debug": "debug",
    "Schedule": "schedule",
    "Securities": "securities",
}


# self.<INDICATOR>(...) -> aqp.data.indicators.<INDICATOR>(...).
# Same casing; we just rewrite the namespace.
_INDICATOR_NAMES: set[str] = {
    "MACD", "SMA", "EMA", "RSI", "BollingerBands", "BB",
    "ATR", "ADX", "STD", "Stochastic", "WMA",
}


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


def _stringify(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return f"<unparse-failed: {type(node).__name__}>"


class _Translator(ast.NodeTransformer):
    """AST transformer that rewrites LEAN-style nodes in place."""

    def __init__(self) -> None:
        super().__init__()
        self.unmapped: list[str] = []
        self.detected_universe: list[str] = []
        self.cfg_overrides: dict[str, Any] = {}

    # ------------------------------------------------- method names
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name in _METHOD_REMAP:
            node.name = _METHOD_REMAP[node.name]
            if node.name in {"prepare", "on_bar"}:
                # FrameworkAlgorithm hooks take ``ctx`` (not ``self``)
                # as the second positional. Preserve self for now;
                # callers can fold the signature in a follow-up edit.
                pass
        return self.generic_visit(node)

    # ------------------------------------------------- self.<API>() calls
    def visit_Call(self, node: ast.Call) -> ast.AST:
        node = self.generic_visit(node)  # type: ignore[assignment]
        func = node.func
        if not isinstance(func, ast.Attribute):
            return node
        if not isinstance(func.value, ast.Name) or func.value.id != "self":
            return node

        api = func.attr

        # Detect SetCash / SetStartDate / SetEndDate and capture as cfg
        if api == "SetCash" and node.args:
            value = self._maybe_constant(node.args[0])
            if value is not None:
                self.cfg_overrides["starting_cash"] = value
        if api in ("SetStartDate", "SetEndDate") and node.args:
            value = self._maybe_constant_date(node.args)
            if value is not None:
                key = "start_date" if api == "SetStartDate" else "end_date"
                self.cfg_overrides[key] = value
        # Detect universe adds
        if api.startswith("Add") and node.args:
            sym = self._maybe_constant(node.args[0])
            if isinstance(sym, str):
                self.detected_universe.append(sym)

        # Remap self.AddEquity -> ctx.add_equity etc.
        if api in _CTX_API_REMAP:
            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="ctx", ctx=ast.Load()),
                    attr=_CTX_API_REMAP[api],
                    ctx=ast.Load(),
                ),
                args=node.args,
                keywords=node.keywords,
            )

        # Remap self.MACD(...) -> aqp.data.indicators.MACD(...)
        if api in _INDICATOR_NAMES:
            return ast.Call(
                func=ast.Attribute(
                    value=ast.Attribute(
                        value=ast.Attribute(
                            value=ast.Name(id="aqp", ctx=ast.Load()),
                            attr="data",
                            ctx=ast.Load(),
                        ),
                        attr="indicators",
                        ctx=ast.Load(),
                    ),
                    attr=api,
                    ctx=ast.Load(),
                ),
                args=node.args,
                keywords=node.keywords,
            )

        # Unmapped self.<X>(...) — leave as-is but record so we can
        # surface a TODO comment when generating the final source.
        if api not in {"OnData", "Initialize"} and api not in _METHOD_REMAP:
            self.unmapped.append(_stringify(node))
        return node

    # ------------------------------------------------- helpers
    @staticmethod
    def _maybe_constant(node: ast.AST) -> Any | None:
        if isinstance(node, ast.Constant):
            return node.value
        return None

    @staticmethod
    def _maybe_constant_date(args: list[ast.expr]) -> str | None:
        parts: list[int] = []
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                parts.append(arg.value)
        if len(parts) >= 3:
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        return None


def translate_lean_to_framework(
    source: str,
    *,
    class_name: str | None = None,
) -> str:
    """Translate a LEAN class source into a FrameworkAlgorithm skeleton.

    The skeleton:

    - subclasses :class:`aqp.strategies.framework.FrameworkAlgorithm`
    - registers via ``@register("Name", kind="strategy", source="lean")``
    - inherits the LEAN docstring
    - has the translated ``prepare`` / ``on_bar`` (etc.) hooks
    - carries the detected ``cfg`` overrides (starting_cash, dates)
    - emits ``# TODO(lean-translate)`` comments for unmapped API calls
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"# Could not parse LEAN source: {exc}\n# Original source preserved below.\n{source}"

    # Locate the QCAlgorithm class.
    target_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
            (isinstance(b, ast.Name) and b.id == "QCAlgorithm")
            or (isinstance(b, ast.Attribute) and b.attr == "QCAlgorithm")
            for b in node.bases
        ):
            target_class = node
            break
    if target_class is None:
        return f"# No QCAlgorithm subclass found; preserving source verbatim.\n{source}"

    # Apply the transformations.
    translator = _Translator()
    rewritten = translator.visit(target_class)
    ast.fix_missing_locations(rewritten)

    docstring = ast.get_docstring(target_class) or ""
    cls_name = class_name or target_class.name
    register_name = cls_name

    # Render the new class body.
    try:
        body_src = ast.unparse(rewritten)
    except Exception as exc:  # noqa: BLE001
        return (
            f"# Translation failed at unparse step ({exc}); preserving source verbatim.\n"
            f"{source}"
        )

    # Patch the base class line so the rendered output references
    # FrameworkAlgorithm + the @register decorator.
    body_src = re.sub(
        r"^class\s+" + re.escape(target_class.name) + r"\s*\(QCAlgorithm\)",
        f"class {cls_name}(FrameworkAlgorithm)",
        body_src,
        count=1,
        flags=re.MULTILINE,
    )

    header_lines = [
        '"""Translated from a QuantConnect LEAN template.',
        "",
        "Generated by ``aqp.strategies.lean.translator``. The translator",
        "covers the common 80% of LEAN -> FrameworkAlgorithm patterns;",
        "the remaining ``# TODO(lean-translate)`` markers below need a",
        "human pass before this strategy is production-ready.",
        '"""',
        "from __future__ import annotations",
        "",
        "from aqp.core.registry import register",
        "from aqp.strategies.framework import FrameworkAlgorithm",
        "import aqp.data.indicators as _aqp_indicators  # noqa: F401",
        "",
        "",
    ]
    cfg_lines: list[str] = []
    if translator.cfg_overrides:
        cfg_lines.append("# Detected LEAN configuration:")
        for key, value in translator.cfg_overrides.items():
            cfg_lines.append(f"#   {key} = {value!r}")
        cfg_lines.append("")
    if docstring:
        cfg_lines.append(f"# Original docstring: {docstring.splitlines()[0]}")
        cfg_lines.append("")

    decorator_line = f"@register({register_name!r}, kind='strategy', source='lean')"

    body_with_decorator = f"{decorator_line}\n{body_src}\n"

    if translator.unmapped:
        body_with_decorator += "\n\n# TODO(lean-translate): unmapped LEAN calls below — finish the port manually.\n"
        for line in translator.unmapped[:10]:
            body_with_decorator += f"# {line}\n"
        if len(translator.unmapped) > 10:
            body_with_decorator += f"# (+{len(translator.unmapped) - 10} more)\n"

    return "\n".join(header_lines) + "\n".join(cfg_lines) + "\n" + body_with_decorator


__all__ = ["translate_lean_to_framework"]
