"""Kill-switch coverage for the new ``/ml/serving/halt-all`` endpoint.

We don't spin a full FastAPI app here — the route just delegates to
:meth:`ServeHandler.halt_all`. The test confirms the delegate path
works AND that the topbar ``KillSwitch`` component has the new entry
in its endpoints list (the canonical fan-out contract).
"""
from __future__ import annotations


def test_serve_handler_halt_all_clears_sessions() -> None:
    from aqp_models.handlers import ServeHandler

    handler = ServeHandler(predict_fn=lambda model, payloads: payloads)
    s1 = handler.start_session(model=object(), model_alias="m1", max_batch_size=2)
    s2 = handler.start_session(model=object(), model_alias="m2", max_batch_size=2)
    halted = ServeHandler.halt_all()
    assert halted >= 2
    # The class-level registry MUST be drained.
    assert s1.session_id not in ServeHandler._sessions  # noqa: SLF001
    assert s2.session_id not in ServeHandler._sessions  # noqa: SLF001


def test_killswitch_component_includes_ml_serving_halt_endpoint() -> None:
    """The Vite KillSwitch fans out to /ml/serving/halt-all per Hard Rule 2.

    The endpoint list is plain TypeScript so we string-match the
    source file. Keeps the test hermetic + dependency-free.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent
        / "aqp_client"
        / "src"
        / "components"
        / "common"
        / "KillSwitch.tsx"
    )
    text = source.read_text(encoding="utf-8")
    assert "/ml/serving/halt-all" in text
