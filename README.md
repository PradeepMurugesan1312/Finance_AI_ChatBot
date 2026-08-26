# AHF Finance Assistant - A2A Server

An [A2A protocol](https://a2a-protocol.org/) server that answers routine
accounts payable, procurement, and general finance questions, grounds every
answer in company policy documents, and escalates to a human when it isn't
confident. Read-only: it never writes back to S4HANA.

See [`BAS_Claude_Build_Prompt.md`](./BAS_Claude_Build_Prompt.md) for the full
scope, architecture, and build order this repo follows.

## Status

**Step 1 of 9 (scaffolding) is complete.** This gives you a working,
protocol-compliant A2A server with a placeholder answer - no RAG, no
Generative AI Hub, no S4HANA tool calls yet. Those are steps 2-4.

## Stack

- **Python 3.11+**, [`a2a-sdk`](https://pypi.org/project/a2a-sdk/) (official
  Python SDK for the A2A protocol) for protocol compliance - agent card
  discovery, JSON-RPC task lifecycle, task store.
- **FastAPI** (via `a2a-sdk[fastapi]`) as the ASGI app / HTTP layer, run by
  **uvicorn**. FastAPI, not a full CAP project: this agent has no OData
  model, so a plain ASGI app is the right amount of framework.
- **pydantic-settings** for env-based config, **structlog** for JSON logs.
- Deploys to Cloud Foundry as a standalone app (buildpack: `python_buildpack`)
  rather than an MTA/CAP deployment - confirm the exact runtime.python
  version your CF org's buildpack offers before step 7 (`cf buildpacks`).

## Project layout

```
src/ahf_agent/
  config.py          env-based Settings (no secrets - those come via CF
                      service bindings once Gen AI Hub / HANA Cloud / MCP
                      Gateway are wired in)
  logging_config.py   structlog JSON setup
  agent_card.py       the A2A Agent Card (identity + skills) Joule discovers
  executor.py         core agent logic - currently a placeholder reply
  server.py           FastAPI app: A2A routes + /healthz
  __main__.py         `python -m ahf_agent` entrypoint
tests/
  test_health.py            liveness probe
  test_agent_card.py        capability discovery contract
  test_executor.py          unit tests on the agent logic directly
  test_a2a_round_trip.py    full discover -> SendMessage round trip
```

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # adjust if needed

python -m ahf_agent
# -> http://localhost:8080/healthz
# -> http://localhost:8080/.well-known/agent-card.json
```

## Testing

```bash
pytest -v
```

## Protocol notes (for whoever registers this with Joule)

- Agent card is served at `/.well-known/agent-card.json` (A2A protocol
  v1.0 well-known path).
- Task lifecycle is JSON-RPC 2.0 over `POST /`, method `SendMessage`
  (protobuf-based A2A v1.0 method names, e.g. `SendMessage`/`GetTask`, not
  the older `message/send` style). Requests must include the header
  `A2A-Version: 1.0`.
- `AgentCapabilities.streaming` and `.push_notifications` are both `false`
  today. Streaming and the async webhook pattern for long-running S4HANA
  lookups are step 5 - **do not** register this agent for a use case that
  assumes either capability until then.

## Open questions for the next steps

Per the build prompt, these need your input before I move past scaffolding
(not needed for step 1, but blocking soon):

- **Step 2 (Generative AI Hub):** deployment details for the GPT 5.2
  deployment reused from the "van" project (deployment URL/ID, resource
  group, auth mechanism).
- **Step 3 (RAG):** confirm SharePoint as the shared-drive source (or name
  the actual platform), and how documents are currently organized (site/
  library structure) so the ingestion connector matches reality.
- **Step 7 (deploy):** Cloud Foundry org/space/route naming per environment
  (dev/test/prod), and how service bindings should be created for the future
  Generative AI Hub / HANA Cloud / Integration Suite credentials.

I'll ask again at each of those steps rather than assuming - flagging now so
none of it is a surprise later.
