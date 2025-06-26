import pytest
from unittest.mock import patch, MagicMock
import threading
from datetime import datetime, timedelta

# main.py에서 사용하는 전역 registry와 start_scheduler를 가져옴
from est_alan_scheduler.scheduler import registry as global_registry, start_scheduler
from est_alan_scheduler.main import main as cli_main # main.py의 main 함수
from est_alan_scheduler.task import Task

@pytest.fixture(autouse=True)
def reset_global_registry_and_patches():
    """
    각 테스트 전에 전역 registry를 초기화하고,
    main.py에서 직접 사용하는 start_scheduler를 mock 처리할 수 있도록 준비.
    """
    import est_alan_scheduler.scheduler # Import here
    original_start_scheduler = est_alan_scheduler.scheduler.start_scheduler

    global_registry.store.clear()
    global_registry._lock = threading.Lock()

    yield # 테스트 실행

    # 테스트 후 원래대로 복원 (필요시)
    # est_alan_scheduler.scheduler.start_scheduler = original_start_scheduler # 복원보다는 patch 사용 권장
    # 전역 registry는 다음 테스트에서 다시 초기화됨


# main() 함수가 start_scheduler를 특정 인자로 호출하는지 테스트
@patch('est_alan_scheduler.main.start_scheduler') # main.py 내에서 참조하는 start_scheduler를 patch
@patch('builtins.print') # print 호출을 가로챔 (선택적)
def test_main_calls_start_scheduler_correctly(mock_print, mock_main_start_scheduler):
    """
    cli_main() 함수가 작업 등록 후 start_scheduler를
    blocking=True로 호출하는지 테스트합니다.
    """
    try:
        cli_main()
    except Exception as e:
        # start_scheduler가 mock되었으므로 실제 blocking 루프는 돌지 않음.
        # 만약 cli_main() 내에서 start_scheduler 이후에 다른 코드가 있다면
        # mock된 start_scheduler가 예외를 발생시키지 않는 한 계속 실행될 것임.
        # 여기서는 start_scheduler 호출까지만 중요.
        pass

    # main.py의 start_scheduler 호출은 interval=1.0, blocking=True 임
    mock_main_start_scheduler.assert_called_once_with(interval=1.0, blocking=True)


# main() 함수가 데모 작업을 registry에 등록하는지 테스트
@patch('est_alan_scheduler.main.start_scheduler', MagicMock()) # start_scheduler는 실행되지 않도록 mock
@patch('builtins.print')
def test_main_registers_demo_tasks(mock_print): # Removed mock_main_start_scheduler_dummy
    """cli_main() 함수가 데모 작업들을 전역 registry에 등록하는지 테스트합니다."""

    # 테스트 실행 전 registry는 비어있어야 함 (fixture에 의해)
    assert len(global_registry.store) == 0

    cli_main()

    # main.py에 정의된 작업 ID들
    expected_task_ids = [
        "cli_every_7s",
        "cli_run_at_12s",
        "cli_at_daily",
        "cli_failing_18s",
        "cli_use_result_task_22s" # 새로 추가된 작업 ID
    ]

    assert len(global_registry.store) == len(expected_task_ids)
    for task_id in expected_task_ids:
        assert task_id in global_registry.store
        task = global_registry.store[task_id]
        assert isinstance(task, Task)

    # 각 작업의 스케줄링 유형 및 주요 속성 일부 검증 (선택적)
    task1 = global_registry.store["cli_every_7s"]
    assert task1.every == {"seconds": 7}
    assert task1.args == ("Hello from CLI every 7s",)

    task2_id = "cli_run_at_12s"
    task2 = global_registry.store[task2_id]
    assert task2.run_at is not None
    # run_at 시간은 datetime.now() 기준으로 설정되므로 정확한 값 비교는 어려움
    # 대신 타입이나 None이 아닌지만 확인
    assert isinstance(task2.run_at, datetime)
    assert task2.args == (7, 6)

    task3 = global_registry.store["cli_at_daily"]
    assert task3.at is not None # "HH:MM" 형식 문자열
    assert len(task3.at) == 5 # "HH:MM"
    assert task3.depends_on == ["cli_every_7s"]

    task4 = global_registry.store["cli_failing_18s"]
    assert task4.run_at is not None
    assert isinstance(task4.run_at, datetime)
    # func 이름으로 간접 확인 (task.func.__name__)
    assert task4.func.__name__ == "cli_failing_task"

    task5 = global_registry.store["cli_use_result_task_22s"]
    assert task5.run_at is not None
    assert isinstance(task5.run_at, datetime)
    assert task5.func.__name__ == "cli_use_dependency_result"
    assert task5.args == ("The result from cli_run_at_12s was:",)
    assert task5.depends_on == [task2_id] # "cli_run_at_12s" 작업에 의존


# main.py 내에 정의된 실제 함수들이 Task에 잘 할당되는지 확인
# (위의 테스트에서 func.__name__으로 일부 확인했지만, 좀 더 명시적으로)
@patch('est_alan_scheduler.main.start_scheduler', MagicMock())
@patch('builtins.print')
def test_main_task_functions_are_correctly_assigned(mock_print): # Removed mock_main_start_scheduler_dummy
    """cli_main()에서 생성된 Task 객체들이 올바른 함수를 참조하는지 테스트합니다."""
    cli_main()

    # main.py 내부 함수들에 대한 참조를 얻기 위해, main.py를 임포트할 때의 모듈 사용
    # 또는, main() 함수 내에서 함수들이 정의되므로, main()을 실행한 후
    # 등록된 task의 func 속성을 검사

    task_sample = global_registry.store.get("cli_every_7s")
    task_another = global_registry.store.get("cli_run_at_12s")
    task_failing = global_registry.store.get("cli_failing_18s")
    task_use_result = global_registry.store.get("cli_use_result_task_22s") # 새로 추가된 작업

    assert task_sample is not None and task_sample.func.__name__ == "cli_sample_task"
    assert task_another is not None and task_another.func.__name__ == "cli_another_task"
    # cli_sample_task는 task3_cli_at ("cli_at_daily") 에도 사용됨
    task_at_daily = global_registry.store.get("cli_at_daily")
    assert task_at_daily is not None and task_at_daily.func.__name__ == "cli_sample_task"

    assert task_failing is not None and task_failing.func.__name__ == "cli_failing_task"
    assert task_use_result is not None and task_use_result.func.__name__ == "cli_use_dependency_result" # 새 작업 함수 검증

    # 실제 함수 실행 테스트 (선택적, TaskRegistry 테스트에서 더 자세히 다룸)
    # 여기서는 함수가 올바르게 할당되었는지만 확인
    # 예: task_sample.func("test message") 호출 시 print가 발생하거나 특정 값 반환하는지
    # 이 함수들은 main()의 로컬 스코프에 정의되므로, 직접 호출하려면 main() 실행 컨텍스트 필요.
    # Task 객체에 func이 할당되었는지와 그 이름으로 충분.

    # cli_sample_task 실행 시나리오 (간단히)
    # 이 함수는 print를 포함하므로, print를 mock 하여 검증 가능
    # mock_print.reset_mock() # 이전 print 호출 초기화
    # with patch('builtins.print') as specific_print_mock: # 새 mock 사용
    #     # task_sample.func는 main()의 로컬 함수이므로 직접 가져오기 어려움
    #     # 대신, main()을 실행하여 task가 func을 가지게 한 후, 그 func을 호출
    #     # 하지만 이 func은 main()의 클로저이므로, main() 실행이 완료되면 접근이...
    #     # Task 객체에 저장된 callable을 직접 호출
    #     result = task_sample.func("test message for sample task")
    #     specific_print_mock.assert_any_call(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] CLI Task: test message for sample task")
    #     assert "processed" in result # 반환값 일부 확인
    # 위 방식은 datetime.now() 때문에 문자열 매칭이 어려움. func.__name__으로 충분.


if __name__ == "__main__":
    pytest.main(["-v", __file__])
