"""Core agent logic.

This is the step-1 placeholder: it proves out the A2A task lifecycle (receive
a message, respond synchronously) without yet answering from the knowledge
base. Later steps replace `_STUB_REPLY` with:
  - step 3: RAG-grounded answers from the HANA Cloud vector store
  - step 4: S4HANA status lookups via MCP Gateway tools
  - step 6: escalation to a human queue below the confidence bar

Per the project's security requirements, this executor must never place PII
or vendor banking data into a response, and must never invoke a write
operation against S4HANA - both remain true trivially today since no tool
calls exist yet, but every future change here must preserve them.
"""

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.types import Message, Part, Role
from a2a.utils.errors import UnsupportedOperationError

from ahf_agent.logging_config import get_logger

logger = get_logger(__name__)

_STUB_REPLY = (
    "I'm the AHF Finance Assistant. I'm not yet connected to the finance "
    "knowledge base or S4HANA lookups - that lands in later build steps. "
    "Once connected, I'll answer AP, procurement, and finance policy "
    "questions grounded in company documents, or hand you off to a human "
    "if I'm not confident in the answer."
)


class FinanceAssistantExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_text = context.get_user_input()

        # Log metadata only, not the message text: finance questions can
        # reference invoice/PO/vendor numbers, and this keeps raw user
        # content out of logs by default even before real PII filtering
        # (added alongside the S4HANA tools in step 4) exists.
        logger.info(
            "task_received",
            task_id=context.task_id,
            context_id=context.context_id,
            input_length=len(user_text),
        )

        reply = Message(
            message_id=str(uuid.uuid4()),
            context_id=context.context_id,
            task_id=context.task_id,
            role=Role.ROLE_AGENT,
            parts=[Part(text=_STUB_REPLY)],
        )
        await event_queue.enqueue_event(reply)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Nothing long-running exists yet to cancel (that arrives with the
        # step 5 async webhook path), so there is nothing to interrupt.
        raise UnsupportedOperationError()
