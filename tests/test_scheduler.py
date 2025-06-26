import pytest
import time
import threading
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from freezegun import freeze_time # Added import

from est_alan_scheduler.scheduler import start_scheduler, registry as global_registry
from est_alan_scheduler.task import Task, TaskStatus
from est_alan_scheduler.task_registry import TaskRegistry

@pytest.fixture(autouse=True)
def reset_global_registry():
    """
    각 테스트 전에 전역 registry를 초기화합니다.
    이렇게 하면 테스트 간의 상태 공유를 방지할 수 있습니다.
    scheduler.py의 registry는 전역 변수이므로, 각 테스트가 독립적으로 실행되도록
    내부 store를 비우거나 새 인스턴스로 교체해야 합니다.
    여기서는 간단히 store를 비우고 lock을 새로 할당합니다.
    """
    global_registry.store.clear()
    global_registry._lock = threading.Lock() # Lock도 새로 할당하여 이전 테스트의 영향 제거
    yield
    # 테스트 후 정리 (필요한 경우)
    # 백그라운드 스레드가 있다면 종료시켜야 할 수 있음 (start_scheduler에서 daemon=True로 해결)


def test_start_scheduler_non_blocking():
    """start_scheduler(blocking=False)가 백그라운드 스레드에서 tick을 호출하는지 테스트"""
    # registry는 fixture에 의해 초기화됨
    mock_task_func = MagicMock()
    task = Task(id="test_bg_task", every={"milliseconds": 100}, func=mock_task_func) # 0.1초 간격
    global_registry.register(task)

    # start_scheduler는 내부적으로 global_registry를 사용
    # interval을 매우 짧게 주어 테스트 시간 단축
    scheduler_thread = start_scheduler(interval=0.05, blocking=False) # 0.05초마다 tick
    assert scheduler_thread is not None
    assert isinstance(scheduler_thread, threading.Thread)
    assert scheduler_thread.daemon is True # 주 스레드 종료 시 자동 종료
    assert scheduler_thread.is_alive()

    time.sleep(0.3) # 스케줄러가 몇 번 실행될 시간을 줌 (최소 2-3번 tick 예상)

    # mock_task_func가 여러 번 호출되었는지 확인
    # 정확한 호출 횟수는 타이밍 이슈로 단정하기 어려우므로, 최소 1번 이상 호출되었는지 확인
    assert mock_task_func.call_count > 1

    # 스케줄러 스레드를 명시적으로 중지하는 기능이 현재 없으므로,
    # 데몬 스레드에 의존하여 테스트 종료 시 함께 종료되도록 함.
    # 테스트 환경에서는 스레드가 계속 실행되는 것을 막기 위해
    # 실제로는 start_scheduler가 스레드 객체를 반환하고, 이를 join하거나
    # 중단 메커니즘(이벤트 등)을 두는 것이 좋지만, 현재 구현을 기준으로 테스트.

    # 전역 registry의 상태를 확인하여 작업이 실행되었는지 볼 수도 있음
    assert global_registry.store["test_bg_task"].last_run_at is not None
    assert global_registry.store["test_bg_task"].status in [TaskStatus.SUCCESS, TaskStatus.RUNNING]


def test_start_scheduler_blocking_mode_calls_tick():
    """start_scheduler(blocking=True)가 tick을 호출하는지 테스트 (mocking 사용)"""
    # blocking=True는 무한 루프에 빠지므로, loop 자체를 mock하여 테스트

    with patch.object(global_registry, 'tick', MagicMock()) as mock_tick:
        # 루프가 한 번만 실행되고 종료되도록 time.sleep을 mock하여 예외 발생
        with patch('time.sleep', MagicMock(side_effect=KeyboardInterrupt)):
            with pytest.raises(KeyboardInterrupt): # KeyboardInterrupt로 루프 탈출 가정
                start_scheduler(interval=0.01, blocking=True)

    mock_tick.assert_called() # tick이 한 번 이상 호출되었어야 함


@patch('est_alan_scheduler.scheduler.TaskRegistry', spec=TaskRegistry) # TaskRegistry 인스턴스 생성을 mock
def test_start_scheduler_uses_global_registry_instance(MockTaskRegistry):
    """start_scheduler가 전역 'registry' 인스턴스를 사용하는지 확인"""

    # start_scheduler를 호출하면 내부적으로 registry.tick()을 사용해야 함
    # 전역 registry를 우리가 만든 mock_registry로 교체해야 함

    mock_registry_instance = MockTaskRegistry.return_value # 생성자 호출 시 반환될 mock 객체

    # 원래 scheduler 모듈의 전역 registry를 mock_registry_instance로 패치
    with patch('est_alan_scheduler.scheduler.registry', mock_registry_instance):
        with patch('time.sleep', MagicMock(side_effect=KeyboardInterrupt)):
            with pytest.raises(KeyboardInterrupt):
                start_scheduler(interval=0.01, blocking=True)

    mock_registry_instance.tick.assert_called()


# scheduler.py의 if __name__ == "__main__": 블록 내 로직 테스트
# 이 부분은 통합 테스트 성격이 강하며, 직접 실행되는 코드의 동작을 검증.
# 여기서는 해당 블록의 핵심 로직(작업 등록 및 스케줄러 시작)을 가져와 테스트.
# 실제로는 main 함수를 별도로 분리하여 단위 테스트하는 것이 더 일반적임.
# 여기서는 해당 블록이 `python -m est_alan_scheduler.scheduler` 등으로 실행될 때의 동작을 가정.

@patch('est_alan_scheduler.scheduler.start_scheduler') # est_alan_scheduler.scheduler 모듈의 start_scheduler를 mock
@patch('builtins.print') # print 호출을 가로챔 (선택적)
def test_scheduler_module_does_not_auto_start_when_run_as_main(mock_print, mock_start_scheduler_in_scheduler_module):
    """
    scheduler.py를 직접 실행해도 (__main__ 블록이 없으므로)
    start_scheduler가 자동으로 호출되지 않음을 테스트합니다.
    mock_start_scheduler_in_scheduler_module는 est_alan_scheduler.scheduler.start_scheduler의 mock입니다.
    """
    import runpy
    try:
        # scheduler.py를 __main__으로 실행합니다.
        # 이 모듈 내에서 start_scheduler가 호출되면 mock_start_scheduler_in_scheduler_module이 사용됩니다.
        runpy.run_module("est_alan_scheduler.scheduler", run_name="__main__", init_globals=None)
    except Exception as e:
        pytest.fail(f"runpy.run_module for est_alan_scheduler.scheduler failed unexpectedly: {e}")

    # scheduler.py 내에 __main__ 블록이 없으므로, start_scheduler는 호출되지 않아야 합니다.
    mock_start_scheduler_in_scheduler_module.assert_not_called()


# freeze_time을 fixture로 사용하여 테스트 전체에 적용하거나, 특정 테스트에만 컨텍스트 매니저로 사용
@pytest.fixture
def freezer():
    # 특정 시간으로 고정. 예: 2024년 7월 15일 10:00:00
    # 각 테스트 함수에서 with freeze_time("YYYY-MM-DD HH:MM:SS") 형태로 사용 가능
    # 여기서는 전역 fixture로 만들지 않고, 필요시 테스트 함수 내에서 사용하도록 함.
    pass

if __name__ == "__main__":
    pytest.main(["-v", __file__])
