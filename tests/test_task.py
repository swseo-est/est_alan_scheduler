import pytest
from pydantic import ValidationError
from datetime import datetime, timedelta

from est_alan_scheduler.task import Task, TaskStatus

def test_task_creation_with_every_schedule():
    """'every' 스케줄 옵션으로 Task 생성 테스트"""
    task = Task(every={"seconds": 10}, func=lambda: print("Hello"))
    assert task.id is not None
    assert task.every == {"seconds": 10}
    assert task.at is None
    assert task.run_at is None
    assert task.func is not None
    assert task.status == TaskStatus.PENDING
    assert task.args == ()
    assert task.kwargs == {}
    assert task.depends_on == []
    assert task.last_success_at is None
    assert task.last_run_at is None
    assert task.result is None
    assert task.error_message is None
    assert task.history == []

def test_task_creation_with_at_schedule():
    """'at' 스케줄 옵션으로 Task 생성 테스트"""
    task = Task(at="10:30", func=lambda: print("Hello"))
    assert task.at == "10:30"
    assert task.every is None
    assert task.run_at is None
    assert task.status == TaskStatus.PENDING

def test_task_creation_with_run_at_schedule():
    """'run_at' 스케줄 옵션으로 Task 생성 테스트"""
    run_time = datetime.now() + timedelta(hours=1)
    task = Task(run_at=run_time, func=lambda: print("Hello"))
    assert task.run_at == run_time
    assert task.every is None
    assert task.at is None
    assert task.status == TaskStatus.PENDING

def test_task_creation_with_custom_id():
    """사용자 정의 ID로 Task 생성 테스트"""
    custom_id = "my_custom_task_id"
    task = Task(id=custom_id, every={"minutes": 1}, func=lambda: print("Hello"))
    assert task.id == custom_id

def test_task_id_auto_generation():
    """Task ID 자동 생성 테스트"""
    task1 = Task(every={"seconds": 5}, func=lambda: 1)
    task2 = Task(every={"seconds": 5}, func=lambda: 2)
    assert task1.id != task2.id
    assert isinstance(task1.id, str)
    assert len(task1.id) == 32 # UUID4 hex

def test_task_creation_with_args_and_kwargs():
    """args 및 kwargs를 포함한 Task 생성 테스트"""
    def sample_func(a, b, c=None):
        return a + b + (c if c else 0)

    task = Task(
        every={"hours": 1},
        func=sample_func,
        args=(1, 2),
        kwargs={"c": 3}
    )
    assert task.args == (1, 2)
    assert task.kwargs == {"c": 3}
    # 실제 함수 실행은 TaskRegistry에서 테스트

def test_task_at_format_validation():
    """'at' 필드 형식 유효성 검사 테스트"""
    with pytest.raises(ValidationError) as excinfo:
        Task(at="25:00", func=lambda: print("Invalid time"))
    assert "at field must be in HH:MM format" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Task(at="10:30:00", func=lambda: print("Invalid time")) # 초 포함 불가
    assert "at field must be in HH:MM format" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Task(at="10-30", func=lambda: print("Invalid time")) # 구분자 오류
    assert "at field must be in HH:MM format" in str(excinfo.value)

    # 유효한 형식
    task_valid = Task(at="09:00", func=lambda: print("Valid time"))
    assert task_valid.at == "09:00"
    task_valid_pm = Task(at="23:59", func=lambda: print("Valid time PM"))
    assert task_valid_pm.at == "23:59"


def test_task_every_keys_validation():
    """'every' 필드 키 유효성 검사 테스트"""
    with pytest.raises(ValidationError) as excinfo:
        Task(every={"minutesss": 5}, func=lambda: print("Invalid key")) # 오타
    assert "Invalid key 'minutesss' in 'every' field" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Task(every={}, func=lambda: print("Empty dict")) # 빈 딕셔너리
    assert "'every' field cannot be an empty dictionary" in str(excinfo.value)

    # 유효한 키
    task_valid_every = Task(every={"days": 1, "hours": 2, "minutes": 30, "seconds": 15}, func=lambda: print("Valid"))
    assert task_valid_every.every == {"days": 1, "hours": 2, "minutes": 30, "seconds": 15}

def test_task_default_status_is_pending():
    """Task의 기본 상태가 PENDING인지 확인"""
    task = Task(every={"seconds": 1}, func=lambda: None)
    assert task.status == TaskStatus.PENDING

def test_task_optional_fields_default_to_none_or_empty():
    """선택적 필드들의 기본값 확인"""
    task = Task(every={"seconds": 1}, func=lambda: None)
    assert task.last_success_at is None
    assert task.last_run_at is None
    assert task.result is None
    assert task.error_message is None
    assert task.history == []
    assert task.depends_on == []

# Task 모델 자체는 스케줄 옵션 중 하나만 존재해야 한다는 것을 강제하지 않음.
# 이는 TaskRegistry의 register 메서드에서 검증함.
# 따라서 Task 모델 레벨에서는 여러 스케줄 옵션이 동시에 설정된 경우 ValidationError가 발생하지 않음.
def test_task_model_allows_multiple_schedule_options_initially():
    """Task 모델 자체는 여러 스케줄 옵션 동시 설정을 허용 (TaskRegistry에서 검증)"""
    # 이 테스트는 Task 모델의 현재 동작을 명확히 하기 위함.
    # TaskRegistry.register() 에서 이 조합은 거부되어야 함.
    now = datetime.now()
    try:
        Task(
            every={"seconds": 5},
            at="10:00",
            run_at=now,
            func=lambda: print("This should not be directly used with registry")
        )
    except ValidationError:
        pytest.fail("Task model itself should allow multiple schedule options; validation is in TaskRegistry")

def test_task_creation_no_schedule_options_allowed_initially():
    """Task 모델 자체는 스케줄 옵션이 없는 것도 허용 (TaskRegistry에서 검증)"""
    # TaskRegistry.register() 에서 이 조합은 거부되어야 함.
    try:
        Task(func=lambda: print("No schedule"))
    except ValidationError:
        pytest.fail("Task model itself should allow no schedule options; validation is in TaskRegistry")

# 참고: Task 모델은 Pydantic 모델이므로, 필드 타입이 맞지 않으면 ValidationError가 발생.
# 예를 들어 'every'에 문자열을 넣거나, 'func'에 정수를 넣는 등의 테스트는
# Pydantic의 기본 동작이므로 여기서는 명시적으로 모든 케이스를 다루지 않음.
# 주요 비즈니스 로직 관련 유효성 검사에 집중.

if __name__ == '__main__':
    pytest.main()
