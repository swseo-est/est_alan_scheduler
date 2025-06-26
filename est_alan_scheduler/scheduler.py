from est_alan_scheduler.task_registry import TaskRegistry
from datetime import datetime, timedelta
import time
import threading


#  전역 인스턴스
registry = TaskRegistry()


# ────────────────────────────────────────────────────────────────────────
# 백그라운드 루프
# ────────────────────────────────────────────────────────────────────────

def start_scheduler(interval: float = 1.0, blocking: bool = False):
    """interval(기본 1초)마다 registry.tick() 실행"""

    def loop():
        while True:
            registry.tick()
            time.sleep(interval)

    if blocking:
        loop()
    else:
        threading.Thread(target=loop, daemon=True).start()


# ────────────────────────────────────────────────────────────────────────
# 사용 예시
# ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import datetime, timedelta # 명시적 임포트 (Task 생성 시 필요)

    # 예시 함수들
    def add(a: int, b: int):
        result = a + b
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] Task 'add' executed: {a} + {b} = {result}")
        return result

    def mul(x: int, y: int):
        result = x * y
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] Task 'mul' executed: {x} * {y} = {result}")
        return result

    def one_off_action():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] Task 'one_off_action' executed (run_at).")

    def failing_task_example():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] Task 'failing_task_example' executing and will fail.")
        raise ValueError("This is an intentional error for testing purposes.")

    # Task 인스턴스 생성
    # Task ID는 기본적으로 UUID로 자동 생성됩니다. `id="custom_id"`로 지정 가능합니다.

    # 1. 5초마다 실행되는 작업 (every)
    task_every = Task(every={"seconds": 5}, func=add, args=(2, 3), id="task_every_add_5s")
    registry.register(task_every)

    # 2. 특정 시간에 한 번 실행되는 작업 (run_at) - 지금으로부터 10초 뒤
    time_for_run_at = datetime.now() + timedelta(seconds=10)
    task_run_at = Task(run_at=time_for_run_at, func=one_off_action, id="task_run_at_10s")
    registry.register(task_run_at)

    # 3. 매일 특정 시간에 실행되는 작업 (at) - 지금으로부터 약 20초 뒤 (테스트를 위해 동적 설정)
    # 실제 운영 시에는 "HH:MM" 형태의 고정 문자열 사용 (예: "15:30")
    # 여기서는 테스트 편의를 위해 현재 시간 기준 20초 뒤로 설정
    time_for_at_str = (datetime.now() + timedelta(seconds=20)).strftime("%H:%M")
    print(f"DEBUG: 'task_at_daily_mul' will be scheduled for {time_for_at_str} daily.")
    task_at_daily = Task(at=time_for_at_str, func=mul, args=(10, 5), id="task_at_daily_mul")
    # 이 작업은 task_every_add_5s가 한 번이라도 성공한 후에 실행되도록 의존성 추가
    task_at_daily.depends_on = [task_every.id]
    registry.register(task_at_daily)

    # 4. 의도적으로 실패하는 작업 (run_at) - 지금으로부터 15초 뒤
    time_for_failing_task = datetime.now() + timedelta(seconds=15)
    task_failing = Task(run_at=time_for_failing_task, func=failing_task_example, id="task_failing_15s")
    registry.register(task_failing)

    # 5. 의존성이 있지만, 의존하는 작업이 없는 경우 (테스트용, _deps_ready에서 걸러짐)
    # task_orphan_dep = Task(every={"seconds":60}, func=one_off_action, id="orphan_dep", depends_on=["non_existent_task"])
    # try:
    #     registry.register(task_orphan_dep)
    # except Exception as e:
    #     print(f"Error registering orphan_dep: {e}") # _deps_ready 에서 처리되므로 register 시점엔 에러 없음

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] 스케줄러 시작 (Ctrl+C 로 종료)")
    print("등록된 작업 ID 목록:")
    with registry._lock: # Lock을 사용하여 store에 안전하게 접근
        for task_id_in_store in registry.store:
            print(f"  - {task_id_in_store} (Status: {registry.store[task_id_in_store].status})")

    # 스케줄러 시작 (1초 간격, 현재 스레드 블로킹)
    # blocking=False로 하면 백그라운드 스레드에서 실행됩니다.
    start_scheduler(interval=1.0, blocking=True)
