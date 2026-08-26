import pytest

from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue_v2 import EventQueueSource
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
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


async def test_execute_emits_a_completed_task_with_the_reply_as_an_artifact():
    executor = FinanceAssistantExecutor()
    context = _make_context("What is our T&E policy?")
    queue = EventQueueSource()
    try:
        await executor.execute(context, queue)
        task = await queue.dequeue_event()
        working = await queue.dequeue_event()
        artifact_event = await queue.dequeue_event()
        completed = await queue.dequeue_event()
    finally:
        await queue.close(immediate=True)

    # This is the shape Joule's default Dialog Function template parses
    # (apiResponse.body.artifacts[0].parts[0].text), so the event order and
    # task/context IDs staying consistent across events both matter.
    assert isinstance(task, Task)
    assert task.id == context.task_id
    assert task.context_id == context.context_id

    assert isinstance(working, TaskStatusUpdateEvent)
    assert working.status.state == TaskState.TASK_STATE_WORKING

    assert isinstance(artifact_event, TaskArtifactUpdateEvent)
    reply_text = artifact_event.artifact.parts[0].text
    assert "not yet connected" in reply_text

    assert isinstance(completed, TaskStatusUpdateEvent)
    assert completed.status.state == TaskState.TASK_STATE_COMPLETED


async def test_cancel_is_unsupported():
    executor = FinanceAssistantExecutor()
    context = _make_context("cancel me")
    queue = EventQueueSource()
    try:
        with pytest.raises(UnsupportedOperationError):
            await executor.cancel(context, queue)
    finally:
        await queue.close(immediate=True)
