"""Connectivity to SAP Generative AI Hub on SAP AI Core.

Reached via the "GENAICORE" BTP destination (see ahf_agent.destinations) -
this subaccount has no directly bindable `aicore` marketplace service, so AI
Core is consumed the standard cross-subaccount way, through a destination
rather than a service key baked in here.

Supports a native OpenAI-style tool-calling loop: pass `tools` (OpenAI
function-calling schemas) and `tool_executor` (an async callback dispatching
a tool call by name) to let the model call tools - e.g. S/4HANA lookups via
ahf_agent.s4hana - before producing a final answer.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx

from ahf_agent.destinations import DestinationError, resolve_destination
from ahf_agent.logging_config import get_logger

logger = get_logger(__name__)

_API_VERSION = "2023-05-15"

ToolExecutor = Callable[[httpx.AsyncClient, str, dict], Awaitable[str]]


class AICoreError(RuntimeError):
    """Raised when AI Core can't be reached or returns an unusable response."""


async def complete_chat(
    *,
    destination_name: str,
    deployment_id: str,
    resource_group: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_executor: ToolExecutor | None = None,
    max_tokens: int = 800,
    temperature: float = 0.0,
    timeout: float = 45.0,
    max_tool_iterations: int = 5,
) -> str:
    """Calls a GPT deployment's chat completions endpoint via a BTP destination.

    If `tools` is given, loops on tool calls (executing each via
    `tool_executor`) until the model returns a final answer or
    `max_tool_iterations` is exceeded.

    Raises AICoreError on any failure - callers decide how to degrade (e.g.
    escalate to a human) rather than this module guessing at a fallback.
    """
    messages = list(messages)

    async with httpx.AsyncClient() as client:
        try:
            dest = await resolve_destination(client, destination_name)
        except (DestinationError, httpx.HTTPError) as exc:
            raise AICoreError(f"Could not resolve destination {destination_name!r}: {exc}") from exc
        auth_headers = dest["headers"]

        # GENAICORE's destination URL already ends in "/v2" - don't add
        # another "/v2" segment here (confirmed against a working reference
        # in this same subaccount; doing so silently 404s).
        url = f"{dest['url']}/inference/deployments/{deployment_id}/chat/completions"

        for _ in range(max_tool_iterations + 1):
            payload: dict = {
                "messages": messages,
                # GPT 5.2 (an OpenAI reasoning-tier model) rejects the older
                # "max_tokens" param - confirmed via a live 400 from this
                # deployment ("...Use 'max_completion_tokens' instead").
                "max_completion_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            try:
                resp = await client.post(
                    url,
                    params={"api-version": _API_VERSION},
                    headers={
                        **auth_headers,
                        "AI-Resource-Group": resource_group,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "ai_core_call_failed",
                    status_code=exc.response.status_code,
                    body=exc.response.text[:500],
                )
                raise AICoreError(
                    f"AI Core deployment {deployment_id!r} returned "
                    f"{exc.response.status_code}: {exc.response.text[:500]}"
                ) from exc
            except httpx.HTTPError as exc:
                raise AICoreError(f"AI Core request failed: {exc}") from exc

            data = resp.json()
            try:
                message = data["choices"][0]["message"]
            except (KeyError, IndexError) as exc:
                raise AICoreError(f"Unexpected AI Core response shape: {data!r}") from exc

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content") or ""

            if not tool_executor:
                raise AICoreError(
                    f"Model requested tool calls ({[c['function']['name'] for c in tool_calls]}) "
                    "but no tool_executor was provided"
                )

            messages.append(
                {"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls}
            )
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("tool_call", tool=name, args=args)
                result = await tool_executor(client, name, args)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

        raise AICoreError(f"Exceeded {max_tool_iterations} tool-call iterations without a final answer")
