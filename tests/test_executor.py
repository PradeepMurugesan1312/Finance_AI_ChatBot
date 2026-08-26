import pytest

from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue_v2 import EventQueueSource
from a2a.types import Message, Part, Role, SendMessageRequest
from a2a.utils.errors import UnsupportedOperationError

from ahf_agent.executor import FinanceAssistantExecutor


def _make_context(text: str) -> RequestContext:
    request = SendMessageRequest(
        message=Message(
            message_id="test-msg-1",
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
        )
    )
    return RequestContext(call_context=ServerCallContext(), request=request)


async def test_execute_replies_with_stub_message():
    executor = FinanceAssistantExecutor()
    context = _make_context("What is our T&E policy?")
    queue = EventQueueSource()
    try:
        await executor.execute(context, queue)
        event = await queue.dequeue_event()
    finally:
        await queue.close(immediate=True)

    assert isinstance(event, Message)
    assert event.role == Role.ROLE_AGENT
    assert event.task_id == context.task_id
    assert event.context_id == context.context_id
    assert event.parts[0].text
    assert "not yet connected" in event.parts[0].text


async def test_cancel_is_unsupported():
    executor = FinanceAssistantExecutor()
    context = _make_context("cancel me")
    queue = EventQueueSource()
    try:
        with pytest.raises(UnsupportedOperationError):
            await executor.cancel(context, queue)
    finally:
        await queue.close(immediate=True)
