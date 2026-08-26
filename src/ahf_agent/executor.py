"""Core agent logic.

Step 2: answers come from a real GPT 5.2 call through SAP Generative AI Hub
(see ahf_agent.ai_core). Step 4: the model can call live, read-only S4HANA
lookup tools (see ahf_agent.s4hana) for invoice/PO/PR/vendor/payment status.
Still no policy-document grounding - that's step 3 (RAG from the HANA Cloud
vector store), still pending. Step 6 (escalation below a confidence bar) is
also still pending; today the model is instructed to decline plainly rather
than guess, which is a coarser version of the same idea.

The response is a Task carrying an artifact (not a bare Message) because
that's what Joule's default Dialog Function template expects to parse
(`apiResponse.body.artifacts[0].parts[0].text`, per SAP's own Joule/A2A
CodeJam), and it's the same Task/TaskUpdater shape step 5's async webhook
path will extend with additional status updates over time.

Per the project's security requirements, this executor must never place PII
or vendor banking data into a response, and must never invoke a write
operation against S4HANA. The latter is enforced structurally: every S4HANA
tool in ahf_agent.s4hana only ever issues GET requests - there is no write
tool for the model to call even if asked.
"""

import json

from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part
from a2a.utils.errors import UnsupportedOperationError
import httpx

from ahf_agent import ai_core, s4hana
from ahf_agent.config import Settings
from ahf_agent.logging_config import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are the AHF Finance Assistant, answering routine accounts payable, "
    "procurement, and general finance questions for employees.\n\n"
    "You have live, read-only S4HANA lookup tools for: supplier invoice "
    "status, vendor invoice search, payment clearing status, purchase order "
    "status, purchase requisition status, and vendor (business partner) "
    "master data. Use a tool and answer from its real result - never guess a "
    "status, amount, or date. If the user gives a document number, look it "
    "up directly rather than asking for fiscal year or company code up "
    "front; use those to narrow the search only if the user mentions them.\n\n"
    "You do NOT yet have a knowledge base of AP/procurement/finance policy "
    "documents (e.g. T&E policy, PO approval thresholds, vendor onboarding "
    "procedure). If asked a policy or \"how do I...\" question that isn't a "
    "live S4HANA lookup, say plainly that you don't have that document "
    "grounded yet and the answer will need a human - never invent policy "
    "details.\n\n"
    "You are read-only: never claim to create, approve, reject, block, "
    "unblock, or pay anything, even if asked directly. Keep answers brief "
    "and never request or repeat PII or vendor banking details."
)

_ESCALATION_REPLY = (
    "I couldn't reach the finance model just now, so I don't want to guess "
    "at a policy or account answer. Please route this to the AP/procurement "
    "team directly, or try again shortly."
)


class FinanceAssistantExecutor(AgentExecutor):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def _s4hana_tool_executor(self, client: httpx.AsyncClient, name: str, args: dict) -> str:
        result = await s4hana.execute_tool(client, self._settings.s4hana_destination_name, name, args)
        return json.dumps(result)

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

        try:
            reply = await ai_core.complete_chat(
                destination_name=self._settings.ai_core_destination_name,
                deployment_id=self._settings.llm_deployment_id,
                resource_group=self._settings.ai_core_resource_group,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                tools=s4hana.TOOL_SCHEMAS,
                tool_executor=self._s4hana_tool_executor,
            )
        except ai_core.AICoreError as exc:
            logger.error("ai_core_unreachable", task_id=context.task_id, error=str(exc))
            reply = _ESCALATION_REPLY

        await updater.add_artifact(
            parts=[Part(text=reply)],
            name="answer",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Nothing long-running exists yet to cancel (that arrives with the
        # step 5 async webhook path), so there is nothing to interrupt.
        raise UnsupportedOperationError()
