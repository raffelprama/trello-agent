"""Registry + dispatch for in-process A2A specialists."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.agents.base import A2AMessage, A2AResponse, BaseAgent

logger = logging.getLogger(__name__)


class AgentBus:
    """Maps agent name -> specialist; logs structured [a2a] lines."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, name: str, agent: BaseAgent) -> None:
        self._agents[name] = agent
        agent.bus = self

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def dispatch(self, msg: A2AMessage) -> A2AResponse:
        agent = self._agents.get(msg.to)
        t0 = time.perf_counter()
        logger.info(
            "[a2a] dispatch task=%s from=%s to=%s ask=%s inputs=%s",
            msg.task_id,
            msg.frm,
            msg.to,
            msg.ask,
            _preview_dict(msg.context.get("_resolved_inputs") or msg.context),
        )
        if agent is None:
            ms = (time.perf_counter() - t0) * 1000
            logger.warning("[a2a] unknown agent=%s after %.0fms", msg.to, ms)
            return A2AResponse(
                task_id=msg.task_id,
                frm=msg.to,
                status="error",
                data={},
                error=f"Unknown agent: {msg.to}",
            )
        try:
            out = agent.handle(msg)
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            logger.exception("[a2a] handler error task=%s to=%s ask=%s %.0fms", msg.task_id, msg.to, msg.ask, ms)
            return A2AResponse(
                task_id=msg.task_id,
                frm=msg.to,
                status="error",
                data={},
                error=str(e),
            )
        ms = (time.perf_counter() - t0) * 1000
        keys = list((out.data or {}).keys())[:20]
        logger.info(
            "[a2a] reply task=%s from=%s status=%s data_keys=%s duration_ms=%.0f",
            msg.task_id,
            out.frm,
            out.status,
            keys,
            ms,
        )
        return out


def _preview_dict(d: Any, max_len: int = 400) -> str:
    if not isinstance(d, dict):
        return repr(d)[:max_len]
    try:
        s = str({k: d[k] for k in list(d.keys())[:12]})
        return s[:max_len]
    except Exception:
        return "{...}"


def create_default_bus(factory: Callable[[], dict[str, BaseAgent]] | None = None) -> AgentBus:
    """Build bus with Trello specialists only (orchestrator/answer/reflection are separate)."""
    from app.agents.trello.attachment_agent import AttachmentAgent
    from app.agents.trello.batch import BatchAgent
    from app.agents.trello.board import BoardAgent
    from app.agents.trello.card import CardAgent
    from app.agents.trello.checklist import ChecklistAgent
    from app.agents.trello.comment import CommentAgent
    from app.agents.trello.custom_field_agent import CustomFieldAgent
    from app.agents.trello.label import LabelAgent
    from app.agents.trello.list_agent import ListAgent
    from app.agents.trello.member import MemberAgent
    from app.agents.trello.notification_agent import NotificationAgent
    from app.agents.trello.organization_agent import OrganizationAgent
    from app.agents.trello.search_agent import SearchAgent
    from app.agents.trello.webhook_agent import WebhookAgent

    bus = AgentBus()
    agents: dict[str, BaseAgent]
    if factory:
        agents = factory()
    else:
        agents = {
            "member": MemberAgent(),
            "board": BoardAgent(),
            "list": ListAgent(),
            "card": CardAgent(),
            "checklist": ChecklistAgent(),
            "label": LabelAgent(),
            "comment": CommentAgent(),
            "custom_field": CustomFieldAgent(),
            "webhook": WebhookAgent(),
            "organization": OrganizationAgent(),
            "search": SearchAgent(),
            "notification": NotificationAgent(),
            "attachment": AttachmentAgent(),
            "batch": BatchAgent(),
        }
    for name, ag in agents.items():
        bus.register(name, ag)
    return bus


_default_bus: AgentBus | None = None


def get_default_bus() -> AgentBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = create_default_bus()
    return _default_bus
