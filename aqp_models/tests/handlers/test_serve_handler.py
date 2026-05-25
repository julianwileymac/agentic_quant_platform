"""ServeHandler continuous-batching + halt semantics."""
from __future__ import annotations

import time

from aqp_models.handlers import ServeHandler


class _SumModel:
    def predict(self, payloads):
        return [sum(p) for p in payloads]


def test_session_start_and_predict_single() -> None:
    handler = ServeHandler(predict_fn=_SumModel().predict)
    session = handler.start_session(
        model=_SumModel(), model_alias="sum", max_batch_size=4, max_wait_ms=10
    )
    try:
        result = session.submit([1, 2, 3], timeout=5)
        assert result == 6
        assert session.served_count == 1
    finally:
        handler.stop_session(session.session_id)


def test_session_batch_demux() -> None:
    handler = ServeHandler(predict_fn=_SumModel().predict)
    session = handler.start_session(
        model=_SumModel(), model_alias="sum", max_batch_size=8, max_wait_ms=15
    )
    try:
        # Submit two requests rapidly to fan them into one batch.
        results = []

        def _submit(value):
            results.append(session.submit([value], timeout=5))

        import threading

        threads = [threading.Thread(target=_submit, args=(i,)) for i in (10, 20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == [10, 20]
    finally:
        handler.stop_session(session.session_id)


def test_halt_all_marks_session_halted() -> None:
    handler = ServeHandler(predict_fn=_SumModel().predict)
    handler.start_session(
        model=_SumModel(), model_alias="sum", max_batch_size=2, max_wait_ms=5
    )
    handler.start_session(
        model=_SumModel(), model_alias="sum2", max_batch_size=2, max_wait_ms=5
    )
    halted = ServeHandler.halt_all()
    assert halted >= 1
    # Give the scheduler loops time to drain.
    time.sleep(0.05)
