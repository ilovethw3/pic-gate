"""
PicGate async task persistence.
"""

import json
import calendar
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AsyncTask


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str) -> Optional[Any]:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _timestamp(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    return calendar.timegm(value.utctimetuple())


def task_to_response(task: AsyncTask) -> Dict[str, Any]:
    """Serialize a task for polling clients."""
    return {
        "id": task.task_id,
        "object": "picgate.task",
        "type": task.task_type,
        "status": task.status,
        "created": _timestamp(task.created_at),
        "started_at": _timestamp(task.started_at),
        "finished_at": _timestamp(task.finished_at),
        "result": _json_load(task.result_json),
        "error": _json_load(task.error_json),
    }


async def mark_incomplete_tasks_failed(db: AsyncSession) -> int:
    """Fail tasks that cannot resume after a process restart."""
    result = await db.execute(
        select(AsyncTask).where(AsyncTask.status.in_(("queued", "running")))
    )
    tasks = result.scalars().all()
    if not tasks:
        return 0

    error_payload = _json_dump({
        "message": "Task was interrupted by server restart",
        "type": "interrupted",
        "status_code": 500,
    })
    finished_at = datetime.utcnow()

    for task in tasks:
        task.status = "failed"
        task.error_json = error_payload
        task.finished_at = finished_at

    await db.commit()
    return len(tasks)


class TaskStore:
    """Small repository for async task state transitions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, task_type: str, request_payload: Dict[str, Any]) -> AsyncTask:
        task = AsyncTask(
            task_id=f"task_{uuid.uuid4().hex}",
            task_type=task_type,
            status="queued",
            request_json=_json_dump(request_payload),
            created_at=datetime.utcnow(),
        )
        self.db.add(task)
        await self.db.commit()
        return task

    async def get_task(self, task_id: str) -> Optional[AsyncTask]:
        result = await self.db.execute(
            select(AsyncTask).where(AsyncTask.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def mark_running(self, task_id: str) -> Optional[AsyncTask]:
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = "running"
        task.started_at = datetime.utcnow()
        await self.db.commit()
        return task

    async def mark_succeeded(self, task_id: str, result_payload: Dict[str, Any]) -> Optional[AsyncTask]:
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = "succeeded"
        task.result_json = _json_dump(result_payload)
        task.error_json = ""
        task.finished_at = datetime.utcnow()
        await self.db.commit()
        return task

    async def mark_failed(self, task_id: str, error_payload: Dict[str, Any]) -> Optional[AsyncTask]:
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = "failed"
        task.error_json = _json_dump(error_payload)
        task.finished_at = datetime.utcnow()
        await self.db.commit()
        return task
