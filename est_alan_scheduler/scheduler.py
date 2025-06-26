from est_alan_scheduler.task_registry import TaskRegistry
import time
import threading


def start_scheduler(registry: TaskRegistry, interval: float = 1.0, blocking: bool = False):
    """interval(기본 1초)마다 registry.tick() 실행"""

    def loop():
        while True:
            registry.tick()
            time.sleep(interval)

    if blocking:
        loop()
    else:
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        return thread


