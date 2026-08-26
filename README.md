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
  executor.py         core agent logic - currently a placeholder reply,
                      returned as a completed Task + artifact (the shape
                      Joule's Dialog Function template parses)
  server.py           FastAPI app: A2A routes + /healthz
  __main__.py         `python -m ahf_agent` entrypoint
tests/
  test_health.py            liveness probe
  test_agent_card.py        capability discovery contract
  test_executor.py          unit tests on the agent logic directly
  test_a2a_round_trip.py    full round trip, both as Joule actually calls
                             it (message/send) and the native v1.0 method
joule/
  README.md                 how to register this agent as a Joule capability
  da.sapdas.yaml             digital assistant manifest
  ahf_finance_capability/    scenario + agent-request function + system alias
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

## Joule Studio integration

This agent is built specifically to be registered as a Joule capability -
see [`joule/README.md`](./joule/README.md) for the BTP Destination, IAS
App2App trust, and `joule deploy` setup, and the YAML files it references.
The two things that make the agent code itself Joule-compatible, verified
against SAP's own Joule/A2A CodeJam and blog docs:

- **Wire compatibility**: Joule's A2A client currently sends the v0.3
  JSON-RPC method name `message/send`, not this SDK's default v1.0 name
  `SendMessage`. `server.py` passes `enable_v0_3_compat=True` to
  `create_jsonrpc_routes` so both work on the same endpoint - dropping that
  flag would make this agent silently fail against real Joule traffic while
  still passing a naive test written against the v1.0 method name.
- **Response shape**: Joule's default Dialog Function template extracts the
  reply via the SpEL expression `apiResponse.body.artifacts[0].parts[0].text`.
  `executor.py` therefore responds with a completed `Task` carrying an
  artifact (via `TaskUpdater`), not a bare `Message` - both are valid A2A
  responses per the SDK, but only the Task+artifact shape is what Joule's
  template reads.

Other protocol notes:

- Agent card is served at `/.well-known/agent-card.json` (A2A protocol
  v1.0 well-known path - unchanged by the v0.3 JSON-RPC compat above).
- `AgentCapabilities.streaming` and `.push_notifications` are both `false`
  today. Streaming and the async webhook pattern for long-running S4HANA
  lookups are step 5 - **do not** register this agent for a use case that
  assumes either capability until then.
- Joule's synchronous budget for `agent-request` is 60 seconds - matches
  the build prompt's step 5 constraint.

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
