from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

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
    error: Optional[Exception] = None
    history: List[Dict[str, Any]] = []



