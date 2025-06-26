# EST Alan Scheduler

EST Alan Scheduler는 파이썬으로 작성된 간단한 작업 스케줄러 라이브러리입니다. 주기적인 작업, 특정 시간에 실행되는 작업, 또는 일회성 작업을 정의하고 관리할 수 있습니다.

## 주요 기능

-   **다양한 스케줄링 옵션**:
    -   `every`: 특정 간격으로 반복 실행 (예: 5분마다)
    -   `at`: 매일 특정 시간에 실행 (예: "14:30")
    -   `run_at`: 지정된 특정 일시에 한 번 실행
-   **작업 의존성**: 특정 작업이 성공적으로 완료된 후에 다른 작업을 실행하도록 설정 가능
-   **상태 추적**: 각 작업의 실행 상태 (대기, 실행 중, 성공, 실패) 및 이력 관리
-   **유연한 작업 정의**: 실행할 함수와 인자를 자유롭게 지정

## 설치 방법

이 프로젝트를 사용하려면 로컬에 클론한 후 pip를 사용하여 설치할 수 있습니다.

```bash
# 1. 이 저장소를 클론합니다.
#    (예시: git clone https://github.com/your-username/est-alan-scheduler.git)
#    위 URL을 실제 저장소 URL로 변경해주세요.
# 2. 클론된 디렉토리로 이동합니다.
#    cd est-alan-scheduler
# 3. pip를 사용하여 현재 디렉토리에 있는 패키지를 설치합니다.
pip install .
```
`pyproject.toml`에 정의된 의존성(`pydantic`)이 함께 설치됩니다.

## 개발 및 테스트

이 프로젝트의 개발에 참여하거나 테스트를 직접 실행하려면 다음 단계를 따르세요.

### 개발 환경 설정

1.  먼저, 위 "설치 방법"에 따라 프로젝트를 로컬에 클론합니다.
2.  프로젝트 루트 디렉토리에서 다음 명령어를 실행하여 개발 의존성 (테스트 도구 포함)을 설치합니다:
    ```bash
    pip install -e .[test]
    ```
    이렇게 하면 `pytest`, `pytest-cov` (코드 커버리지 측정), `freezegun` (시간 제어) 등의 패키지가 설치됩니다.

### 테스트 실행

모든 단위 테스트 및 통합 테스트를 실행하려면 프로젝트 루트 디렉토리에서 다음 명령어를 사용하세요:

```bash
python -m pytest
```

또는 좀 더 상세한 출력을 원하시면:

```bash
python -m pytest -v
```

### 코드 커버리지 확인

테스트 실행 후 코드 커버리지를 확인하려면 다음 명령어를 사용합니다. `pyproject.toml` 파일에 설정된 대로, 커버리지가 90% 미만이면 명령이 실패합니다.

```bash
python -m pytest --cov=est_alan_scheduler
```
(참고: `pyproject.toml`의 `[tool.pytest.ini_options].addopts`에 이미 coverage 관련 설정이 포함되어 있으므로, 단순 `python -m pytest` 실행으로도 커버리지 보고가 이루어질 수 있습니다. HTML 보고서는 `htmlcov/` 디렉토리에 생성됩니다.)

## 사용 예시

다음은 `est_alan_scheduler`를 사용하여 몇 가지 작업을 스케줄링하는 예시입니다. 이 코드는 프로젝트 루트의 `est_alan_scheduler/scheduler.py` 파일 내의 예시 코드를 기반으로 합니다.

```python
from est_alan_scheduler.scheduler import registry, start_scheduler
from est_alan_scheduler.task import Task
from datetime import datetime, timedelta

# 예시 함수들
def add(a: int, b: int):
    print(f"Executing add({a}, {b}) -> {a + b}")
    return a + b

def multiply(x: int, y: int):
    print(f"Executing multiply({x}, {y}) -> {x * y}")
    return x * y

def log_message(message: str):
    print(f"Logging: {message}")

# 스케줄링할 작업 정의
if __name__ == "__main__":
    # 1. 5초마다 실행되는 작업
    task1 = Task(every={"seconds": 5}, func=add, args=(10, 20))

    # 2. task1이 한 번이라도 성공한 후, 매일 특정 시간에 실행되는 작업
    #    (예시: 현재 시간으로부터 약 1분 후로 설정하여 테스트 용이하게 함)
    #    실제 운영 시에는 "HH:MM" 형식으로 고정된 시간을 사용합니다 (예: "15:00").
    now = datetime.now()
    # 다음 분의 0초로 설정, 또는 현재가 50초 이후면 그 다음 분으로.
    if now.second > 50:
        run_at_minute_for_task2 = (now + timedelta(minutes=2)).replace(second=0, microsecond=0)
    else:
        run_at_minute_for_task2 = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    task2_run_time_str = run_at_minute_for_task2.strftime("%H:%M")
    print(f"Task 2 (multiply) will be scheduled to run daily at: {task2_run_time_str}, after task1 succeeds.")
    task2 = Task(at=task2_run_time_str, func=multiply, args=(7, 8), depends_on=[task1.id])

    # 3. 지금으로부터 30초 뒤에 한 번 실행되는 작업
    run_time_task3 = datetime.now() + timedelta(seconds=30)
    print(f"Task 3 (log_message) will run once at: {run_time_task3.strftime('%Y-%m-%d %H:%M:%S')}")
    task3 = Task(run_at=run_time_task3, func=log_message, args=("One-off task executed!",))

    # 작업 등록
    registry.register(task1)
    registry.register(task2)
    registry.register(task3)

    # 스케줄러 시작 (1초 간격으로 체크)
    # blocking=True로 설정하면 스케줄러가 메인 스레드를 점유합니다.
    # 백그라운드에서 실행하려면 blocking=False로 설정하거나 생략합니다.
    print(f"스케줄러를 시작합니다 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})... (Ctrl+C로 종료)")
    start_scheduler(interval=1.0, blocking=True)
```

위 코드를 `example.py`와 같은 파일로 저장하고 실행(`python example.py`)하면, `add` 함수가 5초마다 호출되고, `task1`이 성공적으로 한 번 실행된 후 지정된 시간에 `multiply` 함수가 (매일 그 시간에) 호출됩니다. `log_message` 함수는 30초 후에 한 번 실행됩니다.

## 주요 구성 요소

### `Task` (`est_alan_scheduler/task.py`)

`Task` 클래스는 스케줄러에 의해 관리되는 개별 작업을 정의하는 데이터 모델입니다. `pydantic.BaseModel`을 상속받아 데이터 유효성 검사 및 직렬화를 지원합니다.

-   **주요 속성**:
    -   `id`: 작업의 고유 식별자 (UUID4 hex 문자열, 자동 생성).
    -   **스케줄링 옵션** (이 중 하나만 지정해야 함):
        -   `every: Optional[Dict[str, int]]`: 반복 실행 간격을 지정합니다. `timedelta`에 전달될 수 있는 딕셔너리 (예: `{"minutes": 5}`, `{"hours": 1, "seconds": 30}`).
        -   `at: Optional[str]`: 매일 특정 시간에 작업을 실행합니다. "HH:MM" 형식의 문자열 (예: `"14:30"`).
        -   `run_at: Optional[datetime]`: 특정 날짜 및 시간에 작업을 한 번 실행합니다. `datetime` 객체.
    -   `func: Callable[..., Any]`: 스케줄에 따라 실행될 파이썬 함수.
    -   `args: Tuple[Any, ...]`: `func`에 전달될 위치 인자.
    -   `kwargs: Dict[str, Any]`: `func`에 전달될 키워드 인자.
    -   `depends_on: List[str]`: 이 작업이 실행되기 전에 성공적으로 완료되어야 하는 다른 작업들의 `id` 목록.
    -   `status: TaskStatus`: 작업의 현재 상태 (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`). 기본값은 `PENDING`.
    -   `last_success_at: Optional[datetime]`: 작업이 마지막으로 성공한 시각.
    -   `last_run_at: Optional[datetime]`: 작업이 마지막으로 실행된 시각 (성공/실패 무관).
    -   `result: Any`: `func` 실행 후 반환된 결과.
    -   `error: Optional[Exception]`: `func` 실행 중 발생한 예외.
    -   `history: List[Dict[str, Any]]`: 작업 실행 이력 (실행 시각, 상태, 결과/오류 등).

### `TaskRegistry` (`est_alan_scheduler/task_registry.py`)

`TaskRegistry` 클래스는 `Task` 객체들을 저장하고, 실행 조건을 판단하며, 실제 실행을 관리합니다.

-   **주요 메서드**:
    -   `register(task: Task) -> Task`: 새로운 작업을 레지스트리에 등록합니다. 스케줄 옵션이 정확히 하나만 지정되었는지 확인합니다.
    -   `tick()`: 스케줄러 루프의 각 간격마다 호출됩니다. 모든 등록된 작업을 순회하며 다음을 수행합니다:
        -   `_should_run(task: Task, now: datetime) -> bool`: 현재 시간을 기준으로 작업의 시간 조건 ( `every`, `at`, `run_at`)이 충족되었는지 판단합니다.
        -   `_deps_ready(task: Task) -> bool`: 작업의 `depends_on`에 명시된 모든 선행 작업들이 한 번 이상 성공했는지 확인합니다.
        -   `_execute(task: Task)`: 시간 조건과 의존성 조건이 모두 충족된 작업을 실행합니다. 실행 중 상태를 `RUNNING`으로 변경하고, 실행 후 결과를 바탕으로 `SUCCESS` 또는 `FAILED`로 상태를 업데이트하며, `result`, `error`, `last_run_at`, `last_success_at`, `history` 등의 정보를 기록합니다. 선행 작업의 결과는 `dep_<task_id>` 형태의 키워드 인자로 전달됩니다.

### `scheduler` (`est_alan_scheduler/scheduler.py`)

이 모듈은 `TaskRegistry`의 전역 인스턴스(`registry`)를 생성하고, 스케줄러 루프를 시작하는 함수를 제공합니다.

-   `start_scheduler(interval: float = 1.0, blocking: bool = False)`:
    -   `interval`: 스케줄러가 `registry.tick()`을 호출하는 간격(초 단위, 기본값 1.0초).
    -   `blocking`: `True`이면 현재 스레드에서 루프를 실행하여 이후 코드를 차단합니다. `False`(기본값)이면 백그라운드 데몬 스레드에서 루프를 실행합니다.
    -   이 함수는 내부적으로 `registry.tick()`을 주기적으로 호출하는 루프를 실행합니다.
-   **전역 `registry` 인스턴스**: `est_alan_scheduler.scheduler.registry`를 임포트하여 애플리케이션의 다른 부분에서 작업 등록에 사용할 수 있습니다.

사용 예시 코드(`scheduler.py`의 `if __name__ == "__main__":` 블록 또는 위 README의 예시)는 이러한 구성 요소들을 활용하여 실제 작업을 정의하고 스케줄러를 실행하는 방법을 보여줍니다.

## 향후 개선 방향 (아이디어)

-   **영속성 (Persistence)**: 현재 작업 상태 및 이력은 메모리 내에만 저장됩니다. 애플리케이션 재시작 시 정보가 유실되지 않도록 데이터베이스(SQLite, Redis 등)나 파일 시스템을 이용한 영속성 계층을 추가할 수 있습니다.
-   **분산 환경 지원**: 여러 스케줄러 인스턴스가 동일한 작업 목록을 공유하고 실행할 수 있도록 Redis나 ZooKeeper와 같은 외부 시스템을 이용한 잠금(locking) 및 상태 동기화 메커니즘을 고려할 수 있습니다.
-   **동적 작업 관리**: 실행 중에 작업을 추가, 제거, 수정할 수 있는 API 또는 인터페이스를 제공할 수 있습니다.
-   **실패 처리 및 재시도**: 작업 실패 시 자동 재시도 로직 (횟수 제한, 지연 시간 증가 등)을 구현할 수 있습니다.
-   **웹 UI/API**: 작업을 모니터링하고 관리할 수 있는 웹 기반 사용자 인터페이스 또는 REST API를 제공할 수 있습니다.
-   **더 다양한 스케줄링 옵션**: Cron 표현식 지원 등 더 복잡하고 유연한 스케줄링 옵션을 추가할 수 있습니다.
-   **알림**: 작업 성공/실패 시 이메일, 슬랙 등 외부 시스템으로 알림을 보내는 기능을 추가할 수 있습니다.
