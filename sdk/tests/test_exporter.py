import threading

from agent_tracer.exporter import BatchExporter


class RecordingExporter(BatchExporter):
    """BatchExporter with the network layer replaced by an in-memory sink."""

    def __init__(self, **kwargs):
        self.batches = []
        self.lock = threading.Lock()
        super().__init__("http://collector.invalid", "at_test", **kwargs)

    def post_batch(self, body):
        with self.lock:
            self.batches.append(body)


def test_batches_and_flush():
    exporter = RecordingExporter(flush_interval=5.0)  # rely on flush, not timer
    for i in range(7):
        exporter.enqueue_span({"trace_id": "t" * 32, "span_id": f"{i:016d}", "status": "ok"})
    exporter.enqueue_trace({"trace_id": "t" * 32, "name": "run"})

    assert exporter.flush(timeout=5)
    all_spans = [s for b in exporter.batches for s in b["spans"]]
    all_traces = [t for b in exporter.batches for t in b["traces"]]
    assert len(all_spans) == 7
    assert len(all_traces) == 1
    exporter.shutdown()


def test_trace_updates_deduped_within_batch():
    exporter = RecordingExporter(flush_interval=5.0)
    exporter.enqueue_trace({"trace_id": "a" * 32, "name": "run"})
    exporter.enqueue_trace({"trace_id": "a" * 32, "status": "ok"})
    assert exporter.flush(timeout=5)
    all_traces = [t for b in exporter.batches for t in b["traces"]]
    assert len(all_traces) == 1
    assert all_traces[0] == {"trace_id": "a" * 32, "name": "run", "status": "ok"}
    exporter.shutdown()


def test_shutdown_flushes_pending():
    exporter = RecordingExporter(flush_interval=60.0)
    exporter.enqueue_span({"trace_id": "b" * 32, "span_id": "1" * 16, "status": "ok"})
    exporter.shutdown()
    all_spans = [s for b in exporter.batches for s in b["spans"]]
    assert len(all_spans) == 1


def test_enqueue_after_shutdown_is_noop():
    exporter = RecordingExporter(flush_interval=60.0)
    exporter.shutdown()
    exporter.enqueue_span({"trace_id": "c" * 32, "span_id": "2" * 16})
    assert exporter.flush() is True  # doesn't hang


def test_max_batch_size_splits_batches():
    exporter = RecordingExporter(flush_interval=5.0, max_batch_size=10)
    for i in range(25):
        exporter.enqueue_span({"trace_id": "d" * 32, "span_id": f"{i:016d}"})
    assert exporter.flush(timeout=5)
    total = sum(len(b["spans"]) for b in exporter.batches)
    assert total == 25
    exporter.shutdown()
