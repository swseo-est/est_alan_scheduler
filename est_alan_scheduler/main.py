from datetime import datetime, timedelta
from est_alan_scheduler.task import Task # Task 클래스 임포트
from est_alan_scheduler.scheduler import registry, start_scheduler # 전역 registry와 start_scheduler 임포트

def main():
    """
    est-alan-scheduler CLI의 메인 함수.
    데모용 작업을 등록하고 스케줄러를 시작합니다.
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] est-alan-scheduler CLI 데모 시작...")

    # 예시 함수 정의
    def cli_sample_task(message: str):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] CLI Task: {message}")
        return f"Message '{message}' processed at {datetime.now()}"

    def cli_another_task(a: int, b: int):
        result = a * b
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] CLI Another Task: {a} * {b} = {result}")
        return result

    def cli_failing_task():
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] CLI Failing Task: 이 작업은 의도적으로 실패합니다.")
        raise RuntimeError("CLI 데모용 의도된 실패")

    def cli_use_dependency_result(message_prefix: str, dep_cli_run_at_12s): # 관례에 따라 의존성 결과 인자명 사용
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        # dep_cli_run_at_12s는 'cli_run_at_12s' 작업의 결과값을 받게 됩니다.
        print(f"[{timestamp}] CLI Use Result Task: {message_prefix} {dep_cli_run_at_12s}")
        return f"Processed dependency result: {dep_cli_run_at_12s}"

    # Task 등록
    task1_cli = Task(
        every={"seconds": 7},
        func=cli_sample_task,
        args=("Hello from CLI every 7s",),
        id="cli_every_7s"
    )
    registry.register(task1_cli)

    task2_cli_run_at_time = datetime.now() + timedelta(seconds=12)
    task2_cli = Task(
        run_at=task2_cli_run_at_time,
        func=cli_another_task,
        args=(7, 6),
        id="cli_run_at_12s"
    )
    registry.register(task2_cli)

    # CLI용 'at' 작업 (테스트 용이하게 현재 시간 + 25초로 설정)
    cli_at_time_str = (datetime.now() + timedelta(seconds=25)).strftime("%H:%M")
    print(f"DEBUG (CLI): 'cli_at_daily' will be scheduled for {cli_at_time_str} daily, dependent on {task1_cli.id}.")
    task3_cli_at = Task(
        at=cli_at_time_str,
        func=cli_sample_task,
        args=(f"Daily greeting at {cli_at_time_str}",),
        id="cli_at_daily",
        depends_on=[task1_cli.id] # task1_cli가 한 번 성공해야 실행
    )
    registry.register(task3_cli_at)

    task4_cli_failing_time = datetime.now() + timedelta(seconds=18)
    task4_cli_failing = Task(
        run_at=task4_cli_failing_time,
        func=cli_failing_task,
        id="cli_failing_18s"
    )
    registry.register(task4_cli_failing)

    # 작업 간 데이터 공유 예시 Task
    # task2_cli (cli_run_at_12s)가 실행된 후, 그 결과를 받아 사용
    task5_cli_use_result_time = datetime.now() + timedelta(seconds=22) # task2_cli 이후 실행되도록 시간 설정
    task5_cli_use_result = Task(
        run_at=task5_cli_use_result_time,
        func=cli_use_dependency_result,
        args=("The result from cli_run_at_12s was:",), # 첫 번째 인자 (message_prefix)
        # 'dep_cli_run_at_12s'는 TaskRegistry에 의해 자동으로 kwargs로 전달됨
        id="cli_use_result_task_22s",
        depends_on=[task2_cli.id] # task2_cli.id는 "cli_run_at_12s"
    )
    registry.register(task5_cli_use_result)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] 등록된 CLI 작업들:")
    with registry._lock: # 스레드 안전하게 접근
        for task_id, task_obj in registry.store.items():
            # main.py에서 생성된 작업들만 간략히 표시하거나, ID로 구분
            if task_id.startswith("cli_"):
                 print(f"  - {task_id} (Status: {task_obj.status}, Schedule: "
                       f"{'every ' + str(task_obj.every) if task_obj.every else ''}"
                       f"{'at ' + str(task_obj.at) if task_obj.at else ''}"
                       f"{'run_at ' + str(task_obj.run_at) if task_obj.run_at else ''}"
                       f", Depends: {task_obj.depends_on if task_obj.depends_on else 'None'}" # 의존성 정보 추가
                       f")")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] 스케줄러를 blocking 모드로 시작합니다. (Ctrl+C 로 종료)")

    # 스케줄러 시작 (1초 간격, blocking 모드)
    start_scheduler(interval=1.0, blocking=True)

if __name__ == '__main__':
    # 이 파일이 직접 실행될 때도 main() 함수 호출
    main()
