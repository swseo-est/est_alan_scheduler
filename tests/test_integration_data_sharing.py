import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from est_alan_scheduler.scheduler import registry as global_registry, start_scheduler
from est_alan_scheduler.main import main as cli_main
from est_alan_scheduler.task import Task, TaskStatus

@pytest.fixture(autouse=True)
def setup_for_integration_test():
    global_registry.store.clear()
    global_registry._lock = threading.Lock()
    yield

@patch('builtins.print') # 테스트 중 print 억제
def test_data_sharing_between_cli_tasks(mock_print):
    """
    cli_main()으로 등록된 작업 간의 데이터 공유 (의존성 결과 전달)를 테스트합니다.
    'cli_run_at_12s' -> 'cli_use_result_task_22s'
    """

    # freezegun으로 시간 고정. cli_main()은 이 시간을 기준으로 run_at 등을 설정.
    with freeze_time("2024-01-01 10:00:00") as frozen_time:
        # 1. cli_main()을 호출하여 데모 작업들을 등록.
        #    main.py 내부의 start_scheduler는 mock 처리하여 실제 실행 방지.
        with patch('est_alan_scheduler.main.start_scheduler') as mock_main_start_scheduler:
            cli_main()

        mock_main_start_scheduler.assert_called_once_with(interval=1.0, blocking=True)

        task_producer_id = "cli_run_at_12s"
        task_consumer_id = "cli_use_result_task_22s"

        assert task_producer_id in global_registry.store
        assert task_consumer_id in global_registry.store

        task_producer = global_registry.store[task_producer_id]
        task_consumer = global_registry.store[task_consumer_id]

        # 작업 등록 시점의 run_at 시간 확인 (디버깅용)
        # print(f"Producer ({task_producer_id}) run_at: {task_producer.run_at}") # 예상: 10:00:12
        # print(f"Consumer ({task_consumer_id}) run_at: {task_consumer.run_at}") # 예상: 10:00:22

        # 2. 실제 스케줄러를 non-blocking 모드로 실행
        scheduler_thread = start_scheduler(interval=1.0, blocking=False) # 1초마다 tick
        assert scheduler_thread is not None and scheduler_thread.is_alive()

        # --- 시간 진행 및 상태 확인 ---

        # 시간: 10:00:00 (초기) -> 아무 작업도 실행 안됨
        time.sleep(0.1) # 스케줄러 스레드 동작 시간
        assert task_producer.status == TaskStatus.PENDING
        assert task_consumer.status == TaskStatus.PENDING

        # 시간을 13초 진행 (10:00:13) -> task_producer (10:00:12 실행)가 실행되어야 함
        frozen_time.tick(delta=timedelta(seconds=13))
        time.sleep(1.1) # 스케줄러가 tick(1초 간격)을 처리하고 작업 완료할 시간

        # print_task_statuses("After 13s (producer should run)")
        assert task_producer.status == TaskStatus.SUCCESS, \
            f"Producer task status was {task_producer.status}, history: {task_producer.history}"
        assert task_producer.result == 42 # 7 * 6 = 42 (main.py 로직)
        assert task_consumer.status == TaskStatus.PENDING # 아직 실행 시간 안됨

        # 시간을 추가로 10초 진행 (총 23초, 시간: 10:00:23)
        # -> task_consumer (10:00:22 실행)가 실행되어야 함
        frozen_time.tick(delta=timedelta(seconds=10)) # 10:00:13 -> 10:00:23
        time.sleep(1.1) # 스케줄러가 tick을 처리하고 작업 완료할 시간

        # print_task_statuses(f"After 23s (consumer should run, current time: {datetime.now()})")
        # print(f"Consumer history: {task_consumer.history}")

        assert task_consumer.status == TaskStatus.SUCCESS, \
             f"Consumer task status was {task_consumer.status}, history: {task_consumer.history}"
        # task_consumer의 result는 "Processed dependency result: 42" 여야 함
        assert task_consumer.result == "Processed dependency result: 42"

        # 마지막 실행 기록에서 전달된 인자 확인 (간접적)
        # cli_use_dependency_result(message_prefix: str, dep_cli_run_at_12s)
        # 실제 함수 호출은 history에 남지 않으므로, print된 내용이나 result로 확인.
        # 여기서는 result로 확인.

        # (선택적) mock_print를 사용하여 실제 출력된 메시지 검증도 가능
        # 어떤 print가 어디서 호출되었는지 구분하기 위해 더 정교한 mock 설정 필요할 수 있음.
        # mock_print.assert_any_call(expected_string_containing_42)


def print_task_statuses(header=""): # 디버깅용 헬퍼 (필요시 사용)
    # print(f"--- {header} ---")
    # for task_id, task_obj in global_registry.store.items():
    #     if task_id.startswith("cli_"):
    #         print(f"Task '{task_id}': Status={task_obj.status}, LastRun={task_obj.last_run_at}, Result={task_obj.result}")
    # print("--------------------")
    pass

if __name__ == '__main__':
    pytest.main(["-v", __file__])
