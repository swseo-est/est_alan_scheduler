import pytest
from datetime import datetime, timedelta, time as dtime
from unittest.mock import MagicMock, call
from freezegun import freeze_time

from est_alan_scheduler.task import Task, TaskStatus
from est_alan_scheduler.task_registry import TaskRegistry

# 헬퍼 함수
def create_mock_task(**kwargs):
    """지정된 속성으로 모의 Task 객체를 생성합니다."""
    params = {
        "func": MagicMock(return_value="success"),
        "id": None, # Task가 자동 생성하도록
        "every": None, "at": None, "run_at": None, # 스케줄 옵션
        "args": (), "kwargs": {}, "depends_on": [],
        "status": TaskStatus.PENDING,
        "last_success_at": None, "last_run_at": None,
        "result": None, "error_message": None, "history": []
    }

    # 제공된 kwargs로 기본값 업데이트
    # 스케줄 옵션 중 하나만 설정되도록 주의해야 함 (테스트 케이스에서)
    schedule_options_count = sum(1 for opt in ["every", "at", "run_at"] if kwargs.get(opt) is not None)

    if "id" not in kwargs: # id가 명시적으로 제공되지 않으면 자동 생성되도록 None 유지
        del params["id"]


    # Task 생성 시 유효한 스케줄 옵션을 갖도록 조정
    # 이 헬퍼는 주로 Task 객체를 registry에 넣기 전에 사용하므로,
    # Task 모델 자체의 유연성보다는 registry의 요구사항에 맞추는 것이 편리.
    # 다만, register 메서드 테스트 시에는 의도적으로 잘못된 옵션을 전달해야 함.
    # 여기서는 kwargs에 스케줄 옵션이 하나만 있거나, 아예 없다고 가정하고 Task를 생성.
    # 만약 여러개 있거나, register 테스트용으로 잘못된 옵션을 만들고 싶다면,
    # 이 헬퍼를 쓰지 않거나, 헬퍼를 더 정교하게 만들어야 함.
    # 지금은 kwargs에 알아서 잘 넣어준다고 가정.

    final_params = {**params, **kwargs}
    # print(f"Creating task with final_params: {final_params}")
    return Task(**final_params)


@pytest.fixture
def registry():
    """테스트를 위한 새로운 TaskRegistry 인스턴스를 제공합니다."""
    return TaskRegistry()

# ─────────────────────────── register 메서드 테스트 ───────────────────────────────

def test_register_task_success(registry: TaskRegistry):
    """성공적인 작업 등록 테스트"""
    task = create_mock_task(every={"seconds": 5}, id="test_task_1")
    registered_task = registry.register(task)
    assert registered_task == task
    assert task.id in registry.store
    assert registry.store[task.id] == task

def test_register_task_no_schedule_option_fails(registry: TaskRegistry):
    """스케줄 옵션이 없는 작업 등록 시 ValueError 발생 테스트"""
    task_no_schedule = Task(func=lambda: "no schedule") # create_mock_task 사용 안함
    with pytest.raises(ValueError, match="Task must specify exactly one of every / at / run_at"):
        registry.register(task_no_schedule)

def test_register_task_multiple_schedule_options_fail(registry: TaskRegistry):
    """여러 스케줄 옵션이 있는 작업 등록 시 ValueError 발생 테스트"""
    task_multiple_schedule = Task(
        every={"seconds": 10},
        at="10:00",
        func=lambda: "multiple schedules"
    ) # create_mock_task 사용 안함
    with pytest.raises(ValueError, match="Task must specify exactly one of every / at / run_at"):
        registry.register(task_multiple_schedule)

def test_register_duplicate_task_id_fails(registry: TaskRegistry):
    """중복 ID로 작업 등록 시 ValueError 발생 테스트"""
    task1 = create_mock_task(id="duplicate_id", every={"seconds": 5})
    registry.register(task1)
    task2 = create_mock_task(id="duplicate_id", at="12:00")
    with pytest.raises(ValueError, match="Task with id 'duplicate_id' already registered."):
        registry.register(task2)

# ─────────────────────────── _deps_ready 메서드 테스트 ────────────────────────────
# _deps_ready는 lock 하에서 호출되므로, 테스트 시 store를 직접 조작

def test_deps_ready_no_dependencies(registry: TaskRegistry):
    """의존성이 없는 작업의 경우 True 반환 테스트"""
    task = create_mock_task(every={"seconds": 1})
    assert registry._deps_ready(task) is True

def test_deps_ready_dependency_not_found(registry: TaskRegistry):
    """의존하는 작업이 존재하지 않을 경우 False 반환 테스트"""
    task = create_mock_task(every={"seconds": 1}, depends_on=["non_existent_dep"])
    # registry.store는 비어있음
    assert registry._deps_ready(task) is False

def test_deps_ready_dependency_not_succeeded(registry: TaskRegistry):
    """의존하는 작업이 성공한 적이 없을 경우 False 반환 테스트"""
    dep_task = create_mock_task(id="dep1", every={"seconds": 10}, last_success_at=None)
    registry.store[dep_task.id] = dep_task
    task = create_mock_task(every={"seconds": 1}, depends_on=[dep_task.id])
    assert registry._deps_ready(task) is False

def test_deps_ready_dependency_succeeded(registry: TaskRegistry):
    """의존하는 작업이 성공했을 경우 True 반환 테스트"""
    dep_task = create_mock_task(id="dep1", every={"seconds": 10}, last_success_at=datetime.now())
    registry.store[dep_task.id] = dep_task
    task = create_mock_task(every={"seconds": 1}, depends_on=[dep_task.id])
    assert registry._deps_ready(task) is True

def test_deps_ready_multiple_dependencies_one_not_succeeded(registry: TaskRegistry):
    """여러 의존성 중 하나라도 실패/미존재 시 False 반환 테스트"""
    dep1_succ = create_mock_task(id="dep1_s", every={"seconds":1}, last_success_at=datetime.now())
    dep2_pend = create_mock_task(id="dep2_p", every={"seconds":1}, last_success_at=None)
    registry.store[dep1_succ.id] = dep1_succ
    registry.store[dep2_pend.id] = dep2_pend

    task = create_mock_task(every={"seconds":1}, depends_on=[dep1_succ.id, dep2_pend.id])
    assert registry._deps_ready(task) is False

def test_deps_ready_multiple_dependencies_all_succeeded(registry: TaskRegistry):
    """여러 의존성이 모두 성공했을 경우 True 반환 테스트"""
    dep1 = create_mock_task(id="dep1", every={"seconds":1}, last_success_at=datetime.now())
    dep2 = create_mock_task(id="dep2", every={"seconds":1}, last_success_at=datetime.now())
    registry.store[dep1.id] = dep1
    registry.store[dep2.id] = dep2

    task = create_mock_task(every={"seconds":1}, depends_on=[dep1.id, dep2.id])
    assert registry._deps_ready(task) is True


# ─────────────────────────── _should_run 메서드 테스트 ────────────────────────────
# _should_run은 lock 하에서 호출되므로, 테스트 시 store를 직접 조작하거나 task 객체만 전달

@freeze_time("2024-07-15 10:00:00")
def test_should_run_run_at_task(registry: TaskRegistry):
    """_should_run: run_at 작업 테스트"""
    # 지정 시간 전
    task_before = create_mock_task(run_at=datetime(2024, 7, 15, 10, 0, 1))
    assert registry._should_run(task_before, datetime.now()) is False

    # 지정 시간 정각
    task_on_time = create_mock_task(run_at=datetime(2024, 7, 15, 10, 0, 0))
    assert registry._should_run(task_on_time, datetime.now()) is True

    # 지정 시간 후
    task_after = create_mock_task(run_at=datetime(2024, 7, 15, 9, 59, 59))
    assert registry._should_run(task_after, datetime.now()) is True

    # 이미 실행 시도된 경우 (last_run_at 설정됨)
    task_already_run = create_mock_task(run_at=datetime(2024, 7, 15, 9, 0, 0), last_run_at=datetime(2024,7,15, 9,0,5))
    assert registry._should_run(task_already_run, datetime.now()) is False

@freeze_time("2024-07-15 10:00:00") # 현재 시각 10:00:00
def test_should_run_at_task(registry: TaskRegistry):
    """_should_run: at 작업 테스트"""
    now = datetime.now() # 2024-07-15 10:00:00

    # 지정 시간 전 (오늘)
    task_before = create_mock_task(at="10:01") # 오늘 10:01:00
    assert registry._should_run(task_before, now) is False

    # 지정 시간 정각 (오늘)
    task_on_time = create_mock_task(at="10:00") # 오늘 10:00:00
    assert registry._should_run(task_on_time, now) is True

    # 지정 시간 후 (오늘)
    task_after = create_mock_task(at="09:59") # 오늘 09:59:00
    assert registry._should_run(task_after, now) is True

    # 오늘 이미 실행된 경우
    task_run_today = create_mock_task(at="09:00", last_run_at=now.replace(hour=9, minute=0, second=5))
    assert registry._should_run(task_run_today, now) is False # 09:00에 실행했으므로, 10:00에는 다시 실행 안함

    # 어제 실행된 경우 (오늘 아직 실행 안됨)
    task_run_yesterday = create_mock_task(at="10:00", last_run_at=now - timedelta(days=1))
    assert registry._should_run(task_run_yesterday, now) is True

    # 시간이 00:00 이고, last_run_at이 어제인 경우
    with freeze_time("2024-07-15 00:00:00"):
        now_midnight = datetime.now()
        task_at_midnight = create_mock_task(at="00:00", last_run_at=now_midnight - timedelta(days=1))
        assert registry._should_run(task_at_midnight, now_midnight) is True

@freeze_time("2024-07-15 10:00:00")
def test_should_run_every_task(registry: TaskRegistry):
    """_should_run: every 작업 테스트"""
    now = datetime.now()

    # 첫 실행
    task_first_run = create_mock_task(every={"seconds": 10})
    assert registry._should_run(task_first_run, now) is True

    # 간격 경과 전
    task_before_interval = create_mock_task(every={"seconds": 10}, last_run_at=now - timedelta(seconds=5))
    assert registry._should_run(task_before_interval, now) is False

    # 간격 경과 정각
    task_on_interval = create_mock_task(every={"seconds": 10}, last_run_at=now - timedelta(seconds=10))
    assert registry._should_run(task_on_interval, now) is True

    # 간격 경과 후
    task_after_interval = create_mock_task(every={"seconds": 10}, last_run_at=now - timedelta(seconds=15))
    assert registry._should_run(task_after_interval, now) is True


def test_should_run_no_schedule_option_returns_false(registry: TaskRegistry):
    """_should_run: 스케줄 옵션 없는 Task는 False 반환 (방어적 코딩)"""
    # Task 생성 시에는 스케줄 옵션이 없어도 되지만, registry.register에서 걸러짐
    # _should_run이 직접 이런 Task를 만날 일은 없지만, 방어적 코드로 False를 반환해야 함
    task_no_schedule = Task(func=lambda: "no schedule") # 스케줄 옵션 없음
    assert registry._should_run(task_no_schedule, datetime.now()) is False


# ─────────────────── _execute_task_logic 메서드 테스트 ──────────────────────
# _execute_task_logic는 lock 외부에서 호출됨. task 상태는 직접 변경.

def test_execute_task_logic_success(registry: TaskRegistry):
    """_execute_task_logic: 성공적인 함수 실행 테스트"""
    mock_func = MagicMock(return_value="Test Success")
    task = create_mock_task(every={"seconds":1}, func=mock_func, args=(1,), kwargs={"b": 2})

    # _execute_task_logic 호출 전, tick에서 설정하는 상태들 모방
    task.status = TaskStatus.RUNNING
    current_run_time = datetime.now()
    task.last_run_at = current_run_time

    dep_results = {"dep_another_task_id": "dependency_result"}

    registry._execute_task_logic(task, dep_results, current_run_time)

    mock_func.assert_called_once_with(1, b=2, dep_another_task_id="dependency_result")
    assert task.status == TaskStatus.SUCCESS
    assert task.result == "Test Success"
    assert task.error_message is None
    assert task.last_success_at is not None
    assert abs(task.last_success_at - datetime.now()) < timedelta(seconds=1) # 거의 현재 시간
    assert len(task.history) == 1
    history_entry = task.history[0]
    assert history_entry["run_at"] == current_run_time
    assert history_entry["status"] == TaskStatus.SUCCESS
    assert history_entry["result"] == repr("Test Success")
    assert history_entry["error"] is None


def test_execute_task_logic_failure(registry: TaskRegistry):
    """_execute_task_logic: 함수 실행 실패 테스트"""
    error_message = "Intentional Test Error"
    mock_func = MagicMock(side_effect=ValueError(error_message))
    task = create_mock_task(every={"seconds":1}, func=mock_func)

    current_run_time = datetime.now()
    task.status = TaskStatus.RUNNING
    task.last_run_at = current_run_time

    registry._execute_task_logic(task, {}, current_run_time)

    mock_func.assert_called_once()
    assert task.status == TaskStatus.FAILED
    assert task.result is None # 실패 시 result는 변경되지 않거나 None
    assert task.error_message == f"ValueError: {error_message}"
    assert task.last_success_at is None # 성공한 적 없음
    assert len(task.history) == 1
    history_entry = task.history[0]
    assert history_entry["run_at"] == current_run_time
    assert history_entry["status"] == TaskStatus.FAILED
    assert history_entry["result"] is None
    assert history_entry["error"] == f"ValueError: {error_message}"

# ───────────────────────────── tick 메서드 테스트 ───────────────────────────────

@freeze_time("2024-07-15 10:00:00")
def test_tick_runs_due_task(registry: TaskRegistry):
    """tick: 실행 시간된 작업 실행 및 상태 업데이트 테스트"""
    mock_func = MagicMock(return_value="OK")
    # 10:00:00에 실행되어야 할 작업
    task = create_mock_task(id="due_task", run_at=datetime(2024, 7, 15, 10, 0, 0), func=mock_func)
    registry.register(task)

    registry.tick() # 현재 시간 2024-07-15 10:00:00

    mock_func.assert_called_once()
    assert task.status == TaskStatus.SUCCESS
    assert task.last_run_at == datetime(2024, 7, 15, 10, 0, 0) # tick 시작 시의 'now'
    assert task.last_success_at is not None
    assert abs(task.last_success_at - datetime.now()) < timedelta(seconds=1) # 실제 성공 시간
    assert len(task.history) == 1
    assert task.history[0]["status"] == TaskStatus.SUCCESS

@freeze_time("2024-07-15 09:59:50") # tick 호출 10초 전
def test_tick_does_not_run_task_not_due(registry: TaskRegistry):
    """tick: 아직 실행 시간 안된 작업은 실행 안 함"""
    mock_func = MagicMock()
    # 10:00:00에 실행되어야 할 작업
    task = create_mock_task(id="not_due_task", run_at=datetime(2024, 7, 15, 10, 0, 0), func=mock_func)
    registry.register(task)

    registry.tick() # 현재 시간 2024-07-15 09:59:50

    mock_func.assert_not_called()
    assert task.status == TaskStatus.PENDING # 초기 상태 유지
    assert task.last_run_at is None

@freeze_time("2024-07-15 10:00:00")
def test_tick_runs_task_with_met_dependencies(registry: TaskRegistry):
    """tick: 의존성 충족된 작업 실행 테스트"""
    dep_func = MagicMock(return_value="Dep Done")
    dep_task = create_mock_task(id="dep1", run_at=datetime(2024,7,15, 9,59,59), func=dep_func) # 이전 tick에서 실행될 것
    dep_task.last_success_at = datetime(2024,7,15, 9,59,59) # 이미 성공했다고 가정
    dep_task.last_run_at = dep_task.run_at # 현재 tick에서 다시 실행되지 않도록 설정 (들여쓰기 수정)
    dep_task.result = "Dep Done"
    dep_task.status = TaskStatus.SUCCESS
    registry.register(dep_task)


    main_func = MagicMock()
    main_task = create_mock_task(
        id="main_task",
        run_at=datetime(2024, 7, 15, 10, 0, 0),
        func=main_func,
        depends_on=["dep1"]
    )
    registry.register(main_task)

    # dep_task가 이미 성공한 상태로 설정
    # registry.store[dep_task.id].status = TaskStatus.SUCCESS # 이미 create_mock_task에서 설정
    # registry.store[dep_task.id].last_success_at = datetime(2024, 7, 15, 9, 59, 59)
    # registry.store[dep_task.id].result = "Dep Done"

    registry.tick() # 현재 시간 10:00:00

    # dep_func는 이 tick에서 호출되지 않아야 함 (이미 실행됨 가정)
    dep_func.assert_not_called() # 만약 이전 tick에서 실행되었다면, 여기서는 호출되지 않음
    main_func.assert_called_once_with(dep_dep1="Dep Done") # 의존성 결과 전달 확인
    assert main_task.status == TaskStatus.SUCCESS

@freeze_time("2024-07-15 10:00:00")
def test_tick_does_not_run_task_with_unmet_dependencies(registry: TaskRegistry):
    """tick: 의존성 미충족 작업은 실행 안 함 (PENDING 유지)"""
    dep_task = create_mock_task(id="dep_unmet", run_at=datetime(2024,7,15, 10,0,0)) # 아직 성공 못함
    registry.register(dep_task)

    main_func = MagicMock()
    main_task = create_mock_task(
        id="main_task_unmet_dep",
        run_at=datetime(2024, 7, 15, 10, 0, 0),
        func=main_func,
        depends_on=["dep_unmet"]
    )
    registry.register(main_task)

    registry.tick() # 현재 시간 10:00:00. dep_task는 이 tick에서 실행되지만, main_task는 다음 tick부터 가능

    main_func.assert_not_called()
    assert main_task.status == TaskStatus.PENDING # 의존성 대기

    # dep_task는 실행되어야 함
    assert dep_task.status == TaskStatus.SUCCESS

    # 다음 tick에서 main_task가 실행되는지 확인
    with freeze_time("2024-07-15 10:00:01"): # 시간 약간 진행
        registry.tick()
        main_func.assert_called_once_with(dep_dep_unmet="success") # dep_task의 기본 mock func 리턴값
        assert main_task.status == TaskStatus.SUCCESS


@freeze_time("2024-07-15 10:00:00")
def test_tick_task_status_running_prevents_re_execution(registry: TaskRegistry):
    """tick: RUNNING 상태인 작업은 tick에서 중복 실행 시도 안 함"""
    mock_func = MagicMock()
    task = create_mock_task(id="running_task", every={"seconds": 1}, func=mock_func)
    registry.register(task)

    # 첫 번째 tick: 작업이 실행되고 RUNNING 상태로 변경된다고 가정
    # 이를 직접 시뮬레이션하기 위해, _execute_task_logic를 호출하지 않고 상태만 변경
    with registry._lock:
        task.status = TaskStatus.RUNNING # 강제로 RUNNING 상태로 설정
        task.last_run_at = datetime.now()

    # 두 번째 tick: 작업이 여전히 RUNNING 상태이므로 실행되지 않아야 함
    registry.tick()
    mock_func.assert_not_called() # _execute_task_logic가 호출되지 않음

    # 상태를 다시 PENDING으로 (또는 SUCCESS/FAILED) 바꾸고 tick을 돌리면 실행되어야 함
    task.status = TaskStatus.PENDING # 또는 SUCCESS/FAILED 후 시간 조건 만족
    # last_run_at을 조정하여 다음 실행이 가능하도록 함
    task.last_run_at = datetime.now() - timedelta(seconds=5)

    with freeze_time("2024-07-15 10:00:05"): # 5초 후
        registry.tick()
        mock_func.assert_called_once() # 이제는 호출되어야 함


@freeze_time("2024-07-15 10:00:00")
def test_tick_handles_dependency_data_preparation_failure(registry: TaskRegistry):
    """tick: 의존성 데이터 준비 중 오류 발생 시 작업 실패 처리 (방어적 코드)"""
    # 이 시나리오는 _deps_ready가 True를 반환했지만, 그 직후 store에서 dep_task를 찾을 수 없는 극단적인 경우
    # (예: 외부에서 store를 직접 조작). 실제로는 거의 발생하기 어렵지만, 코드 커버리지 및 견고성 확인.

    dep_id = "dep_vanished"
    dep_task_placeholder = create_mock_task(id=dep_id, every={"seconds": 1}, last_success_at=datetime.now())

    # _deps_ready가 True를 반환하도록 store에 임시로 추가
    registry.store[dep_id] = dep_task_placeholder

    main_func = MagicMock()
    main_task = create_mock_task(
        id="main_task_dep_vanish",
        run_at=datetime(2024, 7, 15, 10, 0, 0),
        func=main_func,
        depends_on=[dep_id]
    )
    registry.register(main_task)

    # _deps_ready 통과 후, dep_kwargs 수집 전에 의존성 작업이 사라지는 상황 모방
    # registry.tick() 내부 로직을 직접 제어하기 어려우므로,
    # _deps_ready는 통과시키고, _execute_task_logic 전에 store에서 의존성을 제거하여
    # tick 내부의 current_dep_kwargs 생성 시 KeyError가 발생하도록 유도.
    # 이는 tick 내부의 방어 코드를 테스트하기 위함.

    # _deps_ready는 통과할 것 (dep_task_placeholder가 store에 있으므로)
    # 그 후 for dep_id_needed in task.depends_on: 루프에서 self.store[dep_id_needed] 접근 시
    # KeyError가 발생하도록 tick 내부 실행 중간에 store를 변경하는 것은 테스트로 구현하기 매우 복잡.

    # 대신, _deps_ready는 True를 반환하지만, 의존성 작업의 result가 없는 경우 (거의 불가능한 시나리오)
    # 또는 의존성 작업 ID에 해당하는 키가 dep_kwargs에 추가되지 않는 경우를 가정.
    # 현재 코드는 _deps_ready가 True면 last_success_at이 있고, result도 있을 것으로 기대.
    # 명시적 KeyError 시뮬레이션은 tick 로직을 분해해야 가능.

    # 여기서는 _deps_ready가 True를 반환했음에도 불구하고,
    # store에서 의존성 작업이 사라진 경우 (tick 내부의 방어 코드 `KeyError` 블록)를 테스트

    original_get = registry.store.get
    def side_effect_get(key, default=None):
        if key == dep_id and main_task.status == TaskStatus.RUNNING: # main_task가 실행 준비될 때
             # _deps_ready는 통과했지만, 의존성 결과 수집 시에는 없어진 것처럼
            # print(f"Simulating vanishing dependency for key: {key}")
            return None # 또는 raise KeyError 로 더 확실히
        return original_get(key, default)

    # registry.store.get = MagicMock(side_effect=side_effect_get)
    # 위 방식은 store가 dict이므로 get을 mock하기 어려움.
    # 대신, _deps_ready 이후에 store에서 직접 제거

    class PatchedTaskRegistry(TaskRegistry):
        def _get_dep_task_for_kwargs(self, dep_id_needed): # 테스트용 헬퍼 메서드 추가 가정
            # 이 부분은 실제 코드에 없으므로, 테스트를 위해 tick 로직을 약간 수정하거나,
            # 매우 정교한 mocking이 필요.
            # 현재 구조에서는 이 특정 방어 코드를 직접 트리거하기 어려움.
            # _deps_ready에서 dep_task = self.store.get(dep_id) 를 사용하므로,
            # 여기서 None을 반환하면 _deps_ready 자체가 False가 됨.
            # KeyError는 self.store[dep_id_needed] 접근 시 발생.

            # 이 테스트는 현재 구조에서 직접적으로 만들기 매우 까다롭습니다.
            # _deps_ready 통과 후, dep_kwargs를 만드는 루프 `dep_task_obj = self.store[dep_id_needed]`
            # 이 라인에서 KeyError가 발생해야 합니다.
            # 이를 위해서는 _deps_ready가 True를 반환한 후, 해당 store 접근 전에 dep_id가 사라져야 합니다.
            # freezegun만으로는 동시성 이슈나 중간 상태 변경을 모방하기 어렵습니다.
            pass # 이 테스트는 현재 방식으로 구현하기 어려워 보류.

    # 이 테스트 케이스는 현재로서는 안정적으로 구현하기 어려우므로 일단 넘어갑니다.
    # tick 내부의 `except KeyError` 블록은 매우 예외적인 상황에 대한 방어 코드입니다.

    # print(f"Initial dep_task status: {dep_task_placeholder.status}, main_task status: {main_task.status}")
    # registry.tick()
    # print(f"After tick: dep_task status: {dep_task_placeholder.status}, main_task status: {main_task.status}")
    # print(f"Main task error: {main_task.error_message}")

    # main_func.assert_not_called()
    # assert main_task.status == TaskStatus.FAILED
    # assert "Dependency data not found during tick" in main_task.error_message
    pytest.skip("This specific defensive code in tick is hard to trigger reliably in tests.")

# ─────────────────── 동적 작업 관리 테스트 (add_task_dynamically, remove_task_dynamically) ─────

def test_add_task_dynamically_success(registry: TaskRegistry):
    """add_task_dynamically: 성공적인 작업 추가 테스트"""
    task = create_mock_task(id="dynamic_add_1", every={"seconds": 10})
    added_task = registry.add_task_dynamically(task)
    assert added_task == task
    assert task.id in registry.store
    assert registry.store[task.id] == task

def test_add_task_dynamically_duplicate_id_fails(registry: TaskRegistry):
    """add_task_dynamically: 중복 ID 작업 추가 시 ValueError 발생 테스트"""
    task1 = create_mock_task(id="dynamic_dup_id", every={"seconds": 5})
    registry.register(task1) # 먼저 하나 등록
    task2 = create_mock_task(id="dynamic_dup_id", at="10:00")
    with pytest.raises(ValueError, match="Task with id 'dynamic_dup_id' already registered."):
        registry.add_task_dynamically(task2)

def test_add_task_dynamically_invalid_schedule_no_option(registry: TaskRegistry):
    """add_task_dynamically: 스케줄 옵션 없는 작업 추가 시 ValueError 발생 테스트"""
    task_invalid = Task(func=lambda: "no schedule", id="dyn_invalid_1")
    with pytest.raises(ValueError, match="Task must specify exactly one of every / at / run_at"):
        registry.add_task_dynamically(task_invalid)

def test_add_task_dynamically_invalid_schedule_multiple_options(registry: TaskRegistry):
    """add_task_dynamically: 여러 스케줄 옵션 작업 추가 시 ValueError 발생 테스트"""
    task_invalid = Task(
        id="dyn_invalid_2",
        every={"seconds": 10},
        at="12:00",
        func=lambda: "multiple schedules"
    )
    with pytest.raises(ValueError, match="Task must specify exactly one of every / at / run_at"):
        registry.add_task_dynamically(task_invalid)

def test_remove_task_dynamically_existing_task(registry: TaskRegistry):
    """remove_task_dynamically: 존재하는 작업 제거 성공 및 True 반환 테스트"""
    task_id = "dynamic_remove_1"
    task = create_mock_task(id=task_id, every={"seconds": 10})
    registry.register(task)
    assert task_id in registry.store

    result = registry.remove_task_dynamically(task_id)
    assert result is True
    assert task_id not in registry.store

def test_remove_task_dynamically_non_existing_task(registry: TaskRegistry):
    """remove_task_dynamically: 존재하지 않는 작업 제거 시 False 반환 테스트"""
    result = registry.remove_task_dynamically("non_existent_task_id")
    assert result is False

@freeze_time("2024-01-01 10:00:00")
def test_dynamically_added_task_is_executed(registry: TaskRegistry):
    """동적으로 추가된 작업이 tick에 의해 실행되는지 테스트"""
    mock_func_dynamic = MagicMock()
    dynamic_task_id = "dyn_exec_task"
    # 10:00:05 에 실행되도록 설정
    task_to_add = create_mock_task(id=dynamic_task_id, run_at=datetime(2024, 1, 1, 10, 0, 5), func=mock_func_dynamic)

    # 초기 tick (아직 작업 없음)
    registry.tick()
    mock_func_dynamic.assert_not_called()

    # 작업 동적 추가
    registry.add_task_dynamically(task_to_add)
    assert dynamic_task_id in registry.store

    # 시간 진행 없이 바로 tick -> 아직 실행 시간 안됨
    registry.tick() # 현재시간 10:00:00
    mock_func_dynamic.assert_not_called()

    # 시간 진행하여 실행 시간이 되도록 함
    with freeze_time("2024-01-01 10:00:05"):
        registry.tick() # 현재시간 10:00:05
        mock_func_dynamic.assert_called_once()
        assert registry.store[dynamic_task_id].status == TaskStatus.SUCCESS

@freeze_time("2024-01-01 10:00:00")
def test_dynamically_removed_task_is_not_executed(registry: TaskRegistry):
    """동적으로 제거된 작업이 더 이상 tick에 의해 실행되지 않는지 테스트"""
    mock_func_removed = MagicMock()
    removed_task_id = "dyn_removed_task"
    # 10:00:05 에 실행되도록 설정된 작업
    task_to_remove = create_mock_task(id=removed_task_id, run_at=datetime(2024, 1, 1, 10, 0, 5), func=mock_func_removed)
    registry.register(task_to_remove)

    # 작업 제거
    assert registry.remove_task_dynamically(removed_task_id) is True
    assert removed_task_id not in registry.store

    # 시간을 진행시켜 원래 실행되었어야 할 시간으로 이동
    with freeze_time("2024-01-01 10:00:05"):
        registry.tick() # 현재시간 10:00:05
        mock_func_removed.assert_not_called() # 작업이 제거되었으므로 호출되지 않아야 함

    # 제거 후 다시 추가하고 실행되는지 확인 (선택적 심화 테스트)
    readded_task = create_mock_task(id=removed_task_id, run_at=datetime(2024, 1, 1, 10, 0, 10), func=mock_func_removed)
    registry.add_task_dynamically(readded_task)

    with freeze_time("2024-01-01 10:00:10"):
        registry.tick()
        mock_func_removed.assert_called_once() # 이제는 호출되어야 함 (새로 추가된 작업)


if __name__ == '__main__':
    pytest.main(["-v", __file__])
