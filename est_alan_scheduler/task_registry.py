from est_alan_scheduler.task import Task, TaskStatus
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Any # Added Any
import threading


class TaskRegistry:
    """작업을 저장하고 실행을 관리한다."""

    def __init__(self):
        self.store: Dict[str, Task] = {}
        self._lock = threading.Lock()

    # ── 퍼블릭 API ───────────────────────────────────────────────────

    def register(self, task: Task) -> Task:
        """작업 등록. 스케줄 옵션은 하나만 지정돼야 한다."""
        with self._lock:
            if sum(opt is not None for opt in (task.every, task.at, task.run_at)) != 1:
                raise ValueError("Task must specify exactly one of every / at / run_at schedule options")
            if task.id in self.store:
                # 혹은 업데이트를 허용할 것인가? 현재는 중복 ID 시 에러 발생하도록 함 (덮어쓰기 방지)
                raise ValueError(f"Task with id '{task.id}' already registered.")
            self.store[task.id] = task
            return task

    def update(self, task: Task):
        with self._lock:
            if sum(opt is not None for opt in (task.every, task.at, task.run_at)) != 1:
                raise ValueError("Task must specify exactly one of every / at / run_at schedule options")
            self.store[task.id].update(task)

    def delete(self, task_id):
        with self._lock:
            if task_id in self.store.keys():
                del self.store[task_id]

    # ── 내부 유틸 ───────────────────────────────────────────────────

    def _deps_ready(self, task: Task) -> bool:
        """선행 작업이 존재하고, 한 번 이상 성공했는지 검사"""
        # 이 메서드는 self._lock 하에서 호출되어야 함
        for dep_id in task.depends_on:
            dep_task = self.store.get(dep_id)
            if dep_task is None:
                # 의존하는 작업 자체가 존재하지 않음. 이 경우 해당 작업은 실행 불가.
                # 이 상황을 어떻게 처리할지 정책 필요 (예: 로깅 후 False 반환, 작업 상태 FAILED로 변경 등)
                # 여기서는 False를 반환하여 실행되지 않도록 함.
                # print(f"Warning: Dependency task with id '{dep_id}' not found for task '{task.id}'.") # 실제로는 로거 사용
                return False
            if dep_task.last_success_at is None:
                return False
        return True

    def _should_run(self, task: Task, now: datetime) -> bool:
        """
        시간 조건 충족 여부 판단. 충족 시 True 반환.
        Task 상태 변경은 이 함수 외부 (tick 메서드 내)에서 관리.
        이 함수는 self._lock 하에서 호출되어야 함.
        """
        run_condition = False

        # 1) 1회성(run_at) - 지정된 시간 이후에 아직 실행 시도된 적 없으면 실행
        if task.run_at is not None:
            if task.last_run_at is None and now >= task.run_at:
                run_condition = True

        # 2) 매일 고정 시각(at) - 지정된 시간이 되었고, 오늘 아직 실행 시도 안 했으면 실행
        elif task.at is not None:
            # Task 모델 validator가 "HH:MM" 형식을 보장한다고 가정
            hh, mm = map(int, task.at.split(":"))

            # 지정된 실행 시간 (오늘)
            # now가 naive datetime이라고 가정 (현재 코드베이스 전체적으로 naive 사용)
            potential_run_datetime = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

            if now >= potential_run_datetime:  # 지정된 시간이 되었거나 이미 지났다면
                # 오늘 아직 실행 시도하지 않았다면 (last_run_at 기준)
                if not (task.last_run_at and task.last_run_at.date() == now.date()):
                    run_condition = True

        # 3) 간격 반복(every) - 마지막 실행으로부터 interval이 지났거나, 아직 한 번도 실행 안 됐으면 실행
        elif task.every is not None:
            # Task 모델 validator가 'every' 딕셔너리의 유효성을 보장한다고 가정
            interval = timedelta(**task.every)
            if task.last_run_at is None:  # 첫 실행 시도
                run_condition = True
            elif (now - task.last_run_at >= interval):  # 마지막 실행 시도 후 interval 경과
                run_condition = True
        else:
            # 이 경우는 register에서 이미 걸러지지만, 방어적으로 처리.
            # Task 생성 시 스케줄 옵션이 없는 경우에 해당할 수 있음.
            # ValueError를 발생시키기보다 False를 반환하고 로깅하는 것이 tick 루프에 안전.
            # print(f"Warning: Task {task.id} is missing a schedule option.") # 실제로는 로거 사용
            pass # run_condition remains False

        return run_condition

    # _execute는 _execute_task_logic으로 대체/수정될 예정
    def _execute_task_logic(self, task: Task, dep_kwargs: Dict[str, Any], current_run_time: datetime):
        """
        실제 작업 함수를 실행하고 결과를 기록.
        이 함수는 self._lock 외부에서 호출되어야 함.
        task.status는 호출 전에 RUNNING으로, task.last_run_at은 current_run_time으로 설정되어 있어야 함.
        """
        try:
            # dep_kwargs는 tick 메서드에서 미리 준비하여 전달됨
            task.result = task.func(*task.args, **{**task.kwargs, **dep_kwargs})
            task.status = TaskStatus.SUCCESS
            task.last_success_at = datetime.now() # 성공 시각은 실제 성공 직후 시간
            task.error_message = None # 성공 시 이전 오류 메시지 클리어
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error_message = f"{type(exc).__name__}: {exc}"
            # 필요시 traceback 로깅: import traceback; traceback.print_exc() 또는 logger 사용
        finally:
            # history 기록
            # task.last_run_at은 tick에서 설정한 current_run_time 사용
            task.history.append(
                {
                    "run_at": current_run_time, # 작업 실행 시작 시각 (tick에서 전달)
                    "status": task.status,
                    "result": repr(task.result) if task.status == TaskStatus.SUCCESS else None,
                    "error": task.error_message if task.status == TaskStatus.FAILED else None,
                }
            )
            # TODO: history 크기 제한 로직 (필요시 Task 모델에 max_history_entries 추가 후 여기서 처리)

    # ── 루프 한 틱마다 호출 ──────────────────────────────────────────

    def tick(self):
        """모든 작업을 검사하고 실행 여부를 판단하여 실행."""
        now = datetime.now() # 현재 시간은 tick 시작 시 한 번만 가져옴

        tasks_to_execute_info = [] # {'task': task_obj, 'dep_kwargs': {}, 'run_time': now} 저장

        with self._lock: # store 접근 및 task 상태 초기 변경 보호
            for task_id in list(self.store.keys()): # 반복 중 store 변경 회피 위해 key 리스트 복사
                task = self.store.get(task_id)
                if not task:
                    # print(f"Warning: Task with id '{task_id}' found in keys but not in store during tick.") # 로거 사용
                    continue

                if task.status == TaskStatus.RUNNING: # 이미 다른 tick에서 실행 중으로 표시된 작업은 건너뜀
                    # 이것은 task.func가 매우 오래 걸리는 경우, 다음 tick에서 중복 실행 시도를 막기 위함.
                    # 단, 실제 func 실행은 lock 외부이므로, status RUNNING 설정 시점이 중요.
                    continue

                # 시간 조건 및 의존성 조건 확인 (둘 다 lock 하에서)
                if self._should_run(task, now) and self._deps_ready(task):
                    # 실행해야 할 작업으로 결정됨

                    # 선행 작업 결과 수집 (lock 하에서)
                    current_dep_kwargs = {}
                    try:
                        for dep_id_needed in task.depends_on:
                            # _deps_ready가 True를 반환했으므로, 의존성 작업은 존재하고 성공한 적이 있음.
                            # store.get(dep_id_needed)는 None이 아님을 의미.
                            dep_task_obj = self.store[dep_id_needed] # 직접 접근 (get 불필요)
                            current_dep_kwargs[f"dep_{dep_id_needed}"] = dep_task_obj.result
                    except KeyError as e:
                        # _deps_ready에서 걸렀어야 하지만, 만약을 위한 방어 코드.
                        # 이 경우, 작업 실행을 건너뛰고 오류 기록.
                        # print(f"Error preparing dependencies for task {task.id}: {e}. Skipping.") # 로거 사용
                        task.status = TaskStatus.FAILED # 또는 다른 오류 상태
                        task.error_message = f"Dependency data not found during tick: {e}"
                        task.last_run_at = now # 실행 시도는 있었음
                        task.history.append({
                            "run_at": now, "status": task.status, "result": None, "error": task.error_message
                        })
                        continue # 다음 작업으로

                    # 실행 준비 완료. 상태 변경 및 실행 목록에 추가.
                    task.status = TaskStatus.RUNNING     # 실행 중 상태로 변경
                    task.last_run_at = now               # 실행 시각 기록 (이번 tick의 now 사용)
                    if task.error_message and task.status != TaskStatus.FAILED: # 이전 오류가 있었으나 이제 실행되므로 초기화
                        task.error_message = None

                    tasks_to_execute_info.append({'task': task, 'dep_kwargs': current_dep_kwargs, 'run_time': now})
                # else:
                    # _should_run이 False이거나 _deps_ready가 False인 경우,
                    # _should_run 내부에서 PENDING으로 설정되었을 수 있음 (만약 그렇게 수정했다면).
                    # 현재 _should_run은 상태를 변경하지 않으므로, 여기서는 별도 처리 없음.
                    # PENDING 상태는 "시간 조건은 되었으나 의존성 대기 중" 또는 "다음 실행 대기"로 해석될 수 있음.
                    # 만약 _should_run이 True인데 _deps_ready가 False이면, PENDING 상태로 두는 것이 적절.
                    # 이 로직은 tick 시작 시 task.status != RUNNING 조건과 함께 고려.
                    # if self._should_run(task, now) and not self._deps_ready(task) and task.status != TaskStatus.PENDING :
                    #    task.status = TaskStatus.PENDING # 의존성 대기 중 명시

        # 잠금 외부에서 실제 작업 함수들 실행
        for item in tasks_to_execute_info:
            task_to_run = item['task']
            dep_kwargs_for_task = item['dep_kwargs']
            run_time_for_task = item['run_time'] # task.last_run_at과 동일한 값

            # 실제 작업 실행 로직 호출
            # 이 함수는 task의 status, result, error_message, last_success_at, history를 업데이트함.
            self._execute_task_logic(task_to_run, dep_kwargs_for_task, run_time_for_task)

