import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from freezegun import freeze_time # Added import

# 주요 구성 요소 임포트
from est_alan_scheduler.scheduler import registry as global_registry, start_scheduler
from est_alan_scheduler.main import main as cli_main
from est_alan_scheduler.task import Task, TaskStatus

@pytest.fixture(autouse=True)
def setup_for_integration_test():
    """
    각 통합 테스트 전에 전역 registry를 초기화하고,
    필요한 patch 등을 설정합니다.
    """
    # 전역 registry 초기화
    global_registry.store.clear()
    global_registry._lock = threading.Lock()

    # main.py에서 print가 많이 발생하므로, 테스트 중에는 가로챌 수 있음 (선택)
    # with patch('builtins.print', MagicMock()) as mock_print:
    #     yield mock_print
    yield


def test_simple_scheduler_run_with_cli_tasks():
    """
    cli_main()으로 작업 등록 후, 스케줄러를 짧게 실행하여
    'every' 작업이 실행되고 상태가 업데이트되는지 확인하는 통합 테스트.
    """
    # 1. cli_main()을 호출하여 데모 작업들을 등록
    #    start_scheduler가 blocking=True로 호출되므로, 이를 mock 처리해야 함.
    with patch('est_alan_scheduler.main.start_scheduler') as mock_cli_main_start_scheduler:
        cli_main()

    mock_cli_main_start_scheduler.assert_called_once_with(interval=1.0, blocking=True)

    # cli_main에 의해 등록된 작업 중 하나인 'cli_every_7s'를 가져옴
    task_id_to_check = "cli_every_7s"
    assert task_id_to_check in global_registry.store
    task_obj = global_registry.store[task_id_to_check]

    assert task_obj.status == TaskStatus.PENDING # 초기 상태
    assert task_obj.last_run_at is None
    assert task_obj.every == {"seconds": 7}

    # 2. 이제 실제 스케줄러를 non-blocking 모드로 짧게 실행
    #    interval을 짧게 하여 테스트 시간 단축
    #    주의: cli_main()은 자체적으로 start_scheduler(blocking=True)를 호출하려고 하므로,
    #    위에서 mock 처리함. 여기서는 별도로 start_scheduler를 테스트용으로 호출.

    scheduler_thread = start_scheduler(interval=0.1, blocking=False) # 0.1초마다 tick
    assert scheduler_thread is not None and scheduler_thread.is_alive()

    # 'cli_every_7s' 작업은 7초마다 실행.
    # 스케줄러 tick 간격이 0.1초이므로, 7초가 되기 전에 여러 번 tick 발생.
    # 여기서는 7초보다 짧은 시간(예: 1초) 동안 실행하여 아직 실행되지 않았음을 확인하고,
    # 7초가 넘는 시간 동안 실행하여 최소 한 번 실행되었음을 확인.

    time.sleep(1.0) # 1초 대기 - 아직 7초 안됨
    # print(f"After 1s: Task '{task_id_to_check}' status: {task_obj.status}, last_run_at: {task_obj.last_run_at}")
    # 타이밍 이슈로 PENDING이 아닐 수도 있음 (첫 실행은 last_run_at이 없으면 바로 실행되므로)
    # Task의 every는 last_run_at 기준으로 판단. 첫 실행은 last_run_at이 없으므로 즉시 실행 대상.
    # 따라서 1초 후에도 실행되었을 수 있음.

    # 좀 더 긴 시간 대기하여 'every' 조건이 충족되도록 함.
    # 'cli_every_7s'는 첫 tick에서 last_run_at이 없으므로 바로 실행됨.
    # 그 후 7초 간격으로 실행.

    # 초기 실행 확인
    # 스케줄러 시작 후 짧은 시간 (예: 0.5초) 내에 첫 실행이 이루어져야 함.
    time.sleep(0.5) # 스케줄러가 몇 번의 tick을 돌릴 시간

    assert task_obj.last_run_at is not None, "Task should have run at least once shortly after scheduler start"
    first_run_time = task_obj.last_run_at
    assert task_obj.status == TaskStatus.SUCCESS # 또는 RUNNING, func 내용에 따라

    # 추가로 7.5초를 더 기다려 두 번째 실행이 일어나는지 확인
    # (총 대기 시간: 0.5s + 7.5s = 8s)
    time.sleep(7.5)

    assert task_obj.last_run_at is not None
    # print(f"After additional 7.5s: Task '{task_id_to_check}' status: {task_obj.status}, last_run_at: {task_obj.last_run_at}")
    assert task_obj.last_run_at > first_run_time, "Task should have run again after its 'every' interval"
    assert task_obj.status == TaskStatus.SUCCESS # func이 성공한다고 가정

    # 스레드 정리는 daemon=True에 의존.


@patch('builtins.print') # print 억제
def test_dependency_chain_in_cli_tasks(mock_print):
    """
    cli_main()으로 등록된 작업 중 의존성('cli_at_daily' on 'cli_every_7s')이
    올바르게 처리되는지 통합 테스트.
    """
    # 1. 작업 등록 (cli_main 사용, start_scheduler는 mock)
    with patch('est_alan_scheduler.main.start_scheduler', MagicMock()):
        cli_main()

    task_dependent_id = "cli_at_daily"
    task_dependency_id = "cli_every_7s"

    assert task_dependent_id in global_registry.store
    assert task_dependency_id in global_registry.store

    task_dependent = global_registry.store[task_dependent_id]
    task_dependency = global_registry.store[task_dependency_id]

    assert task_dependent.status == TaskStatus.PENDING
    assert task_dependency.status == TaskStatus.PENDING
    assert task_dependent.depends_on == [task_dependency_id]

    # 'cli_at_daily'는 특정 시간 HH:MM에 실행되도록 설정됨.
    # 테스트를 위해 이 시간을 현재 시간 근처로 동적으로 설정하지만,
    # cli_main() 내에서 이미 datetime.now() 기준으로 설정됨.
    # 여기서는 해당 시간이 아직 도래하지 않았고, 의존성도 충족되지 않았다고 가정.

    # 시간을 고정하여 'at' 작업의 실행 시간을 제어해야 함.
    # cli_main()은 실행될 때의 datetime.now()를 사용.
    # 이 테스트에서는 cli_main() 실행 시점과 스케줄러 실행 시점의 시간 흐름을 고려해야 함.

    # freezegun을 사용하여 전체 테스트 시간 흐름을 제어
    # cli_main() 호출 시의 now와 scheduler 실행 시의 now를 다르게 설정 필요

    # 이 테스트는 복잡한 시간 동기화가 필요.
    # 간략화: 의존성 작업이 먼저 성공하고, 그 이후에 의존하는 작업이 실행될 수 있는지만 확인.
    # 'at' 시간 조건은 무시하고, 의존성만 충족되면 실행되는지 (X) -> 'at' 시간도 맞아야 함.

    # 더 간단한 의존성 테스트:
    # 1. 의존성 작업(A)과 의존하는 작업(B)을 만듦. (B는 A에 의존)
    # 2. A, B 모두 지금 당장 실행될 수 있는 시간 조건 (예: run_at=now)
    # 3. 스케줄러 실행.
    # 4. 첫 tick에서 A가 실행되고 SUCCESS. B는 PENDING (의존성 대기).
    # 5. 다음 tick에서 B가 실행되고 SUCCESS.

    # 현재 cli_main의 'cli_at_daily'는 'at' 스케줄이므로, 시간 조건도 중요.
    # 테스트의 편의를 위해 'cli_at_daily'의 'at' 시간을 지금으로부터 매우 가깝게 설정하고,
    # 'cli_every_7s'가 먼저 실행되도록 유도.

    # cli_main()을 다시 호출하여 현재 시간에 맞게 'at' 시간 조정
    # (또는 task_dependent.at 값을 직접 수정 - 하지만 이건 내부 수정이라 권장 안됨)

    # 테스트 단순화를 위해, cli_main()을 사용하지 않고 직접 Task를 만들어서 테스트
    global_registry.store.clear() # 이전 작업들 제거

    mock_dep_func = MagicMock(return_value="Dep Success")
    mock_main_func = MagicMock(return_value="Main Success")

    # 시간을 고정
    with freeze_time("2024-07-15 10:00:00") as frozen_time:
        dep_task = Task(id="dep_A", run_at=datetime.now() + timedelta(seconds=1), func=mock_dep_func) # 10:00:01
        main_task = Task(id="main_B", run_at=datetime.now() + timedelta(seconds=2), func=mock_main_func, depends_on=["dep_A"]) # 10:00:02

        global_registry.register(dep_task)
        global_registry.register(main_task)

        scheduler_thread = start_scheduler(interval=0.5, blocking=False) # 0.5초마다 tick

        # 시간 진행 및 상태 확인
        frozen_time.tick(delta=timedelta(seconds=0.6)) # 시간: 10:00:00.6 (tick 1)
        # dep_A (10:00:01) 아직, main_B (10:00:02) 아직
        # print_task_statuses("After 0.6s")
        assert dep_task.status == TaskStatus.PENDING
        assert main_task.status == TaskStatus.PENDING
        mock_dep_func.assert_not_called()
        mock_main_func.assert_not_called()

        frozen_time.tick(delta=timedelta(seconds=0.5)) # 시간: 10:00:01.1 (tick 2)
        # dep_A 실행되어야 함. main_B는 아직 (시간도 안됐고, 의존성도 이제 막 풀릴 것)
        time.sleep(0.1) # 스케줄러가 tick을 처리할 시간 (실제 스레드이므로 약간의 지연 필요)
        # print_task_statuses("After 1.1s")
        mock_dep_func.assert_called_once()
        assert dep_task.status == TaskStatus.SUCCESS
        assert main_task.status == TaskStatus.PENDING # 아직 시간 안됨 + 이전 tick에서는 의존성 미충족
        mock_main_func.assert_not_called()

        frozen_time.tick(delta=timedelta(seconds=1.0)) # 시간: 10:00:02.1 (tick 3)
        # main_B 실행되어야 함 (시간 도달, 의존성 충족)
        time.sleep(0.1)
        # print_task_statuses("After 2.1s")
        mock_main_func.assert_called_once_with(dep_dep_A="Dep Success") # 의존성 결과 전달 확인
        assert main_task.status == TaskStatus.SUCCESS

        # 스레드 정리 (daemon)

def print_task_statuses(header=""): # 디버깅용 헬퍼
    print(f"--- {header} ---")
    for task_id, task_obj in global_registry.store.items():
        print(f"Task '{task_id}': Status={task_obj.status}, LastRun={task_obj.last_run_at}, LastSuccess={task_obj.last_success_at}, Result={task_obj.result}")
    print("--------------------")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
