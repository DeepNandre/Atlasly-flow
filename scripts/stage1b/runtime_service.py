from __future__ import annotations

from datetime import datetime

from scripts.stage1b.repositories import Stage1BRepository
from scripts.stage1b.runtime_api import post_create_tasks
from scripts.stage1b.runtime_api import post_reassign_task
from scripts.stage1b.runtime_api import run_assignment_overdue_worker
from scripts.stage1b.ticketing_service import AuthContext


class Stage1BRuntimeService:
    """
    Runtime boundary adapter:
    - loads stores from repository,
    - executes Stage 1B runtime API logic,
    - persists resulting state back to repository.
    """

    def __init__(self, repository: Stage1BRepository):
        self.repository = repository

    def post_create_tasks(
        self,
        *,
        letter_id: str,
        request_body: dict[str, object] | None,
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        confidence_threshold: float = 0.75,
        escalation_policy: dict | None = None,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        ticket_store = self.repository.load_ticket_store()
        notification_store = self.repository.load_notification_store()
        status, payload = post_create_tasks(
            letter_id=letter_id,
            request_body=request_body,
            headers=headers,
            auth_context=auth_context,
            ticket_store=ticket_store,
            notification_store=notification_store,
            confidence_threshold=confidence_threshold,
            escalation_policy=escalation_policy,
            now=now,
        )
        self.repository.save_ticket_store(ticket_store)
        self.repository.save_notification_store(notification_store)
        return status, payload

    def post_reassign_task(
        self,
        *,
        task_id: str,
        request_body: dict[str, object] | None,
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        ticket_store = self.repository.load_ticket_store()
        status, payload = post_reassign_task(
            task_id=task_id,
            request_body=request_body,
            headers=headers,
            auth_context=auth_context,
            ticket_store=ticket_store,
            now=now,
        )
        self.repository.save_ticket_store(ticket_store)
        return status, payload

    def run_assignment_overdue_worker(
        self,
        *,
        user_mode: str = "immediate",
        tick_key: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        ticket_store = self.repository.load_ticket_store()
        notification_store = self.repository.load_notification_store()
        result = run_assignment_overdue_worker(
            ticket_store=ticket_store,
            notification_store=notification_store,
            user_mode=user_mode,
            tick_key=tick_key,
            now=now,
        )
        self.repository.save_ticket_store(ticket_store)
        self.repository.save_notification_store(notification_store)
        return result
