"""Core agent logic.

This is the step-1 placeholder: it proves out the A2A task lifecycle (receive
a message, respond synchronously as a completed Task with an artifact)
without yet answering from the knowledge base. Later steps replace
`_STUB_REPLY` with:
  - step 3: RAG-grounded answers from the HANA Cloud vector store
  - step 4: S4HANA status lookups via MCP Gateway tools
  - step 6: escalation to a human queue below the confidence bar

The response is a Task carrying an artifact (not a bare Message) because
that's what Joule's default Dialog Function template expects to parse
(`apiResponse.body.artifacts[0].parts[0].text`, per SAP's own Joule/A2A
CodeJam), and it's the same Task/TaskUpdater shape step 5's async webhook
path will extend with additional status updates over time.

Per the project's security requirements, this executor must never place PII
or vendor banking data into a response, and must never invoke a write
operation against S4HANA - both remain true trivially today since no tool
calls exist yet, but every future change here must preserve them.
"""

from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part
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

        # context.message is always set here: the framework only calls
        # execute() for a send-message request, which always carries one.
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        await updater.add_artifact(
            parts=[Part(text=_STUB_REPLY)],
            name="answer",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Nothing long-running exists yet to cancel (that arrives with the
        # step 5 async webhook path), so there is nothing to interrupt.
        raise UnsupportedOperationError()
