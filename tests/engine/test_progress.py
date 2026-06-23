import tempfile
from pathlib import Path
from auto_qc.qc.engine.progress import (
    create_progress, load_progress, save_progress, has_unfinished, reset_running_batches,
)
from auto_qc.qc.rules.schemas import Progress


def test_create_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = create_progress(tmpdir, total_batches=5)
        assert p.total_batches == 5
        assert p.batch_status["1"] == "pending"
        assert Path(tmpdir, "progress.json").exists()

        loaded = load_progress(tmpdir)
        assert loaded.total_batches == 5


def test_has_unfinished():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert not has_unfinished(tmpdir)  # 没有进度文件
        create_progress(tmpdir, total_batches=3, phase="qc")
        assert has_unfinished(tmpdir)

        p = load_progress(tmpdir)
        p.phase = "done"
        save_progress(tmpdir, p)
        assert not has_unfinished(tmpdir)


def test_reset_running():
    p = Progress(
        total_batches=3,
        batch_status={"1": "done", "2": "running", "3": "pending"},
    )
    reset_running_batches(p)
    assert p.batch_status["2"] == "pending"
    assert p.batch_status["1"] == "done"
    assert p.batch_status["3"] == "pending"
