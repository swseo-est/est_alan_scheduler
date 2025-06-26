from est_alan_scheduler.task import Task, TaskStatus
from datetime import datetime, timedelta, time as dtime
from typing import Dict
import threading


class TaskRegistry:
    """작업을 저장하고 실행을 관리한다."""

    def __init__(self):
        self.store: Dict[str, Task] = {}
        self._lock = threading.Lock()

    # ── 퍼블릭 API ───────────────────────────────────────────────────

    def register(self, task: Task) -> Task:
        """작업 등록. 스케줄 옵션은 하나만 지정돼야 한다."""
        if sum(opt is not None for opt in (task.every, task.at, task.run_at)) != 1:
            raise ValueError("Task must specify exactly one of every / at / run_at")
        self.store[task.id] = task
        return task

    # ── 내부 유틸 ───────────────────────────────────────────────────

    def _deps_ready(self, task: Task) -> bool:
        """선행 작업이 한 번 이상 성공했는지 검사"""
        return all(self.store[dep].last_success_at is not None for dep in task.depends_on)

    def _should_run(self, task: Task, now: datetime) -> bool:
        """시간 조건 충족 여부 판단 + 충족 시 status=PENDING 설정"""
        run_condition = False

        # 1) 1회성(run_at)
        if task.run_at is not None:
            run_condition = task.last_success_at is None and now >= task.run_at

        # 2) 매일 고정 시각(at)
        elif task.at is not None:
            hh, mm = map(int, task.at.split(":"))
            today_fire = datetime.combine(now.date(), dtime(hour=hh, minute=mm))
            if now >= today_fire:
                run_condition = not (
                    task.last_success_at and task.last_success_at.date() == now.date()
                )

        # 3) 간격 반복(every)
        elif task.every is not None:
            interval = timedelta(**task.every)
            run_condition = (
                task.last_success_at is None or (now - task.last_success_at >= interval)
            )
        else:
            raise ValueError("Task missing schedule option")

        # 시간 조건 충족 → PENDING 으로 표시
        if run_condition:
            task.status = TaskStatus.PENDING
        return run_condition

    def _execute(self, task: Task):
        """작업 실행 및 결과 기록"""
        task.status = TaskStatus.RUNNING
        task.last_run_at = datetime.now()
        try:
            dep_kwargs = {f"dep_{d}": self.store[d].result for d in task.depends_on}
            task.result = task.func(*task.args, **{**task.kwargs, **dep_kwargs})
            task.status = TaskStatus.SUCCESS
            task.last_success_at = datetime.now()
        except Exception as exc:  # noqa: BLE001
            task.status = TaskStatus.FAILED
            task.error = exc
        finally:
            task.history.append(
                {
                    "run_at": task.last_run_at,
                    "status": task.status,
                    "result": repr(task.result) if task.status == TaskStatus.SUCCESS else None,
                    "error": repr(task.error) if task.error else None,
                }
            )

    # ── 루프 한 틱마다 호출 ──────────────────────────────────────────

    def tick(self):
        """모든 작업을 검사하고 실행 여부를 판단"""
        now = datetime.now()
        for task in list(self.store.values()):
            if self._should_run(task, now) and self._deps_ready(task):
                self._execute(task)

