"""并发控制——原子化状态管理，硬限制最大并发数"""
from auto_qc.domain.schemas import Progress
from auto_qc.framework.progress import load_progress, save_progress

MAX_CONCURRENCY = 50


class Coordinator:
    """批次分发协调器，原子化控制并发数。"""

    def __init__(self, work_dir: str, max_concurrency: int = MAX_CONCURRENCY):
        self.work_dir = work_dir
        self.max_concurrency = max_concurrency

    def get_next_batches(self) -> list[int]:
        """
        获取下一批可执行的批次 ID 列表（最多 max_concurrency 个）。
        原子化地将 selected → running 状态写入 progress。
        返回空列表表示全部完成。
        """
        progress = load_progress(self.work_dir)

        # 统计当前 running 数
        running_count = sum(
            1 for s in progress.batch_status.values() if s == "running"
        )

        available_slots = self.max_concurrency - running_count
        if available_slots <= 0:
            return []

        # 找到 pending 批次
        next_batches = []
        for bid in sorted(progress.batch_status.keys(), key=int):
            if progress.batch_status[bid] == "pending":
                next_batches.append(int(bid))
                if len(next_batches) >= available_slots:
                    break

        # 原子化标记为 running
        for bid in next_batches:
            progress.batch_status[str(bid)] = "running"

        save_progress(self.work_dir, progress)
        return next_batches

    def mark_done(self, batch_id: int) -> None:
        """标记批次完成。"""
        progress = load_progress(self.work_dir)
        progress.batch_status[str(batch_id)] = "done"
        progress.completed_batches = sum(
            1 for s in progress.batch_status.values() if s == "done"
        )
        if progress.completed_batches >= progress.total_batches:
            progress.phase = "done"
        save_progress(self.work_dir, progress)

    def mark_failed(self, batch_id: int) -> None:
        """标记批次失败（连续 3 次重试都失败后调用）。"""
        progress = load_progress(self.work_dir)
        progress.batch_status[str(batch_id)] = "failed"
        progress.failed_batches.append(batch_id)
        save_progress(self.work_dir, progress)

    def increment_retry(self, batch_id: int) -> int:
        """增加批次重试次数，返回当前次数。"""
        progress = load_progress(self.work_dir)
        current = progress.retry_count.get(str(batch_id), 0) + 1
        progress.retry_count[str(batch_id)] = current
        progress.batch_status[str(batch_id)] = "pending"  # 重置为 pending 等待重跑
        save_progress(self.work_dir, progress)
        return current

    def get_summary(self) -> dict:
        """返回当前状态摘要。"""
        progress = load_progress(self.work_dir)
        statuses = progress.batch_status.values()
        return {
            "total": progress.total_batches,
            "done": sum(1 for s in statuses if s == "done"),
            "running": sum(1 for s in statuses if s == "running"),
            "pending": sum(1 for s in statuses if s == "pending"),
            "failed": sum(1 for s in statuses if s == "failed"),
        }
