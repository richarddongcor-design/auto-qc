"""进度文件读写"""
import json
from datetime import datetime
from pathlib import Path
from auto_qc.qc.domain.schemas import Progress


def create_progress(work_dir: str, total_batches: int, phase: str = "qc") -> Progress:
    """创建新进度文件。"""
    now = datetime.now().isoformat()
    progress = Progress(
        total_batches=total_batches,
        completed_batches=0,
        phase=phase,
        batch_status={str(i): "pending" for i in range(1, total_batches + 1)},
        retry_count={str(i): 0 for i in range(1, total_batches + 1)},
        failed_batches=[],
        started_at=now,
        updated_at=now,
    )
    save_progress(work_dir, progress)
    return progress


def load_progress(work_dir: str) -> Progress:
    """读取进度文件。不存在时返回初始状态。"""
    path = Path(work_dir) / "progress.json"
    if not path.exists():
        return Progress()

    data = json.loads(path.read_text(encoding="utf-8"))
    return Progress(
        total_batches=data.get("total_batches", 0),
        completed_batches=data.get("completed_batches", 0),
        phase=data.get("phase", "init"),
        batch_status=data.get("batch_status", {}),
        retry_count=data.get("retry_count", {}),
        failed_batches=data.get("failed_batches", []),
        started_at=data.get("started_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def save_progress(work_dir: str, progress: Progress) -> None:
    """写入进度文件。"""
    path = Path(work_dir) / "progress.json"
    progress.updated_at = datetime.now().isoformat()
    if not progress.started_at:
        progress.started_at = progress.updated_at

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "total_batches": progress.total_batches,
        "completed_batches": progress.completed_batches,
        "phase": progress.phase,
        "batch_status": progress.batch_status,
        "retry_count": progress.retry_count,
        "failed_batches": progress.failed_batches,
        "started_at": progress.started_at,
        "updated_at": progress.updated_at,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def has_unfinished(work_dir: str) -> bool:
    """检查是否存在未完成的进度。"""
    progress = load_progress(work_dir)
    if progress.phase == "done":
        return False
    if progress.total_batches == 0:
        return False
    return True


def reset_running_batches(progress: Progress) -> Progress:
    """将状态为 'running' 的批次重置为 'pending'（用于断点续跑）。"""
    for bid, status in progress.batch_status.items():
        if status == "running":
            progress.batch_status[bid] = "pending"
    return progress
