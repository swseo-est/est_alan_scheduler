from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Literal

from pydantic import BaseModel, Field, validator

# ────────────────────────────────────────────────────────────────────────
# 모델 정의
# ────────────────────────────────────────────────────────────────────────

class TaskStatus(str, enum.Enum):
    """작업 상태값"""

    PENDING = "pending"     # 시간 조건 충족했으나 선행 작업 대기 중
    RUNNING = "running"     # 실행 중
    SUCCESS = "success"     # 최근 실행 성공
    FAILED = "failed"       # 최근 실행 실패


class Task(BaseModel):
    """스케줄러가 관리하는 작업 정의 (순수 데이터 모델)"""

    # ── 식별자 ─────────────────────────────────────────────────────────
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tags: List[str] = Field(default_factory=list)

    # ── 스케줄 옵션(하나만 선택) ─────────────────────────────────────
    every: Optional[Dict[str, int]] = None   # 예) {"minutes": 5}
    at: Optional[str] = None                 # "HH:MM" → 매일 고정 시각
    run_at: Optional[datetime] = None        # 절대 시각 1회 실행

    # ── 실행 정의 ───────────────────────────────────────────────────
    func: Callable[..., Any]
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = {}
    depends_on: List[str] = []               # 선행 작업 ID 목록

    # ── 런타임 상태(자동 관리) ─────────────────────────────────────
    status: TaskStatus = TaskStatus.PENDING
    last_success_at: Optional[datetime] = None  # 최근 성공 시각
    last_run_at: Optional[datetime] = None      # 최근 실행 시각(성공/실패 모두)
    result: Any = None
    error_message: Optional[str] = None  # 예외 메시지 문자열 저장
    history: List[Dict[str, Any]] = []
    # max_history_entries: int = 50 # 예시: history 크기 제한 옵션 (이번에는 미적용)

    @validator('at')
    def validate_at_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                # 시간 문자열을 datetime.time 객체로 파싱 시도
                datetime.strptime(v, "%H:%M").time()
            except ValueError:
                raise ValueError("at field must be in HH:MM format")
        return v

    @validator('every')
    def validate_every_keys(cls, v: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        if v is not None:
            allowed_keys = {"days", "seconds", "microseconds", "milliseconds", "minutes", "hours", "weeks"}
            for key_present in v.keys():
                if key_present not in allowed_keys:
                    raise ValueError(
                        f"Invalid key '{key_present}' in 'every' field. Allowed keys are: {allowed_keys}"
                    )
            if not v: # 빈 딕셔너리 방지
                raise ValueError("'every' field cannot be an empty dictionary.")
        return v

    def update(self, task: Task):
        self.tags = task.tags

        # ── 스케줄 옵션(하나만 선택) ─────────────────────────────────────
        self.every = task.every
        self.at = task.at
        self.run_at = task.run_at

        # ── 실행 정의 ───────────────────────────────────────────────────
        self.func = task.func
        self.args = task.args
        self.kwargs = task.kwargs
        self.depends_on = task.depends_on

        # ── 런타임 상태(자동 관리) ─────────────────────────────────────
        # 해당 정보는 기존 정보를 그대로 가져옴



