import tempfile
from auto_qc.qc.engine.coordinator import Coordinator
from auto_qc.qc.engine.progress import create_progress


def test_get_next_empty_when_all_done():
    with tempfile.TemporaryDirectory() as tmpdir:
        coordinator = Coordinator(tmpdir)
        create_progress(tmpdir, total_batches=0)
        assert coordinator.get_next_batches() == []


def test_get_next_returns_pending():
    with tempfile.TemporaryDirectory() as tmpdir:
        coordinator = Coordinator(tmpdir, max_concurrency=3)
        create_progress(tmpdir, total_batches=5)
        batches = coordinator.get_next_batches()
        assert batches == [1, 2, 3]  # 最多 3 个


def test_get_next_respects_running():
    with tempfile.TemporaryDirectory() as tmpdir:
        coordinator = Coordinator(tmpdir, max_concurrency=3)
        create_progress(tmpdir, total_batches=5)
        # 第一轮：拿到 1,2,3
        coordinator.get_next_batches()
        # 标记 1 完成后
        coordinator.mark_done(1)
        # 第二轮：应该拿到 4（而非 1,2,3——2,3 还在 running）
        batches = coordinator.get_next_batches()
        assert batches == [4]


def test_mark_done_and_failed():
    with tempfile.TemporaryDirectory() as tmpdir:
        coordinator = Coordinator(tmpdir)
        create_progress(tmpdir, total_batches=3)
        coordinator.get_next_batches()  # 拿出 1,2,3，全部标记 running
        coordinator.mark_done(1)
        coordinator.mark_failed(2)
        summary = coordinator.get_summary()
        assert summary["done"] == 1
        assert summary["failed"] == 1


def test_retry_increment():
    with tempfile.TemporaryDirectory() as tmpdir:
        coordinator = Coordinator(tmpdir)
        create_progress(tmpdir, total_batches=1)
        coordinator.get_next_batches()  # batch 1 → running
        count = coordinator.increment_retry(1)
        assert count == 1
        # batch 1 应该被重置为 pending
        summary = coordinator.get_summary()
        assert summary["pending"] == 1
