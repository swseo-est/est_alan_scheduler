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
    # 예시 함수들
    def add(a: int, b: int):
        print("add", a, b)
        return a + b

    def mul(x: int, y: int):
        print("mul", x, y)
        return x * y

    # 5초마다 실행되는 작업
    t1 = Task(every={"seconds": 5}, func=add, args=(2, 3))

    # t1 이 한 번이라도 성공한 후 하루에 한 번 14:30에 실행
    t2 = Task(at="14:30", func=mul, args=(10, 5), depends_on=[t1.id])

    # 30초 뒤 1회 실행
    t3_time = datetime.now() + timedelta(seconds=30)
    t3 = Task(run_at=t3_time, func=lambda: print("one‑off done"))

    for t in (t1, t2, t3):
        registry.register(t)

    print("스케줄러 시작… (Ctrl+C 로 종료)")
    start_scheduler(blocking=True)
