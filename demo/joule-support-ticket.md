# SAP Support Ticket — Joule Digital Assistant fails to invoke deployed code-based agent

## Component
Joule / Joule Studio — Code-based agent integration ("Bring Your Own Agent" / `agent-request` action type)

## Summary
A Joule capability using the `agent-request` action type consistently fails with a generic
`JCore-4004 / Dialog function execution failed` error immediately after the dialog function
starts, and **zero HTTP requests ever reach the target agent** — confirmed via the target
agent's own access logs across dozens of attempts over several hours. An identically-configured
capability in the same tenant works correctly, and we have ruled out every difference we can
inspect from the client/customer side.

## Environment
- Global account: Sierra Digital, Inc.
- Subaccount: POC (subaccount ID `499a1aaa-8f6d-4906-8f4f-84dd5bdd224f`)
- Joule tenant ID: `118aa8ef-e28b-4841-83a9-aef0893d0548`
- Failing capability: `ahf_finance_assistant_capability` (namespace `joule.ext`, version `1.0.0`)
- Failing scenario: `finance_faq_scenario`
- Failing dialog function: `finance_faq_function`
- Failing destination: `AHF_FINANCE_AGENT_DEV`
- Joule Studio CLI version: 2.0.2

## Symptom
Every chat request that routes to `finance_faq_function` produces:

```json
{
  "code": "JCore - 4004",
  "message": "Request failed to be processed. Please retry after some time",
  "details": [{
    "status_code": "INTERNAL_EXCEPTION",
    "logs": [
      ...,
      { "code": "SCENARIO_SELECTED", ... },
      { "code": "DIALOG_FUNCTION_STARTED", "data": { "parameters": { "contextId": null, "taskId": null } } },
      { "code": "PROCESSING_FAILED", "message": "Dialog function execution failed", "data": {} }
    ]
  }]
}
```

`PROCESSING_FAILED` fires ~0.5-1.5 seconds after `DIALOG_FUNCTION_STARTED`, with an empty
`"data": {}` — no underlying exception, stack trace, or reason code is exposed to the client at
any verbosity level we've found (chat UI "Request Logs" panel or the raw response payload).

## Reproducible log_id / correlation_id values (all show the identical failure)
- `e1d33b53-04be-46fb-89f6-1316dcfcecb3`
- `56f35940-d9be-41f1-b60e-7992e04a7480`
- `a305516c-a07d-4e47-b708-1d26eac4c382`
- `5463872a-a933-4587-b058-a5e0e2d41af4`
- `d29ea818-a55d-47b3-a2e5-890d598eb4bc`
- correlation IDs: `230e85fe-6065-4530-8a16-9dde3b9b9625`, `c2de9a0d-8b75-4cbf-b80a-269314d09434`

## What we have verified (to save your investigation time)

1. **The target agent never receives a request.** The agent (a FastAPI/A2A server on Cloud
   Foundry) logs every inbound HTTP request. Across every failed attempt above, only routine
   `/healthz` polling appears — never a POST to `/` (the A2A JSON-RPC endpoint). This means the
   failure occurs entirely within Joule's own backend, before any outbound call is attempted.

2. **A working reference capability in the same tenant, same pattern, confirmed live and
   working**: `ap_inquiry_agent_a2a` (capability, same schema version, same `agent-request`
   action type, same `agent_type: remote`) successfully calls its own remote agent and returns
   real answers.

3. **Destination configuration is verified identical** between the failing destination
   (`AHF_FINANCE_AGENT_DEV`) and the working one (`APInquiryAgent_A2A`), checked directly in BTP
   Cockpit, not inferred:
   - Type: `HTTP` (both)
   - Proxy Type: `Internet` (both)
   - Authentication: `NoAuthentication` (both)
   - Additional Properties: `HTML5.DynamicDestination=true`, `WebIDEEnabled=true` (both)

4. **Capability structure matches the working reference exactly**, including:
   - `capability_context.yaml` declaring `contextId`/`taskId`
   - `scenarios/*.yaml` with a full `target.parameters` + `capability_context` wiring block
   - `functions/*.yaml` with `parameters`, a `status-update` action, an `agent-request` action
     with a conditional `body` expression, `set-variables`, and a final `message` action
   - `da.sapdas.yaml` structured per the current CLI schema (confirmed the failing capability's
     manifest is schema-valid — `joule deploy` compiles and deploys it successfully every time)

5. **Deploys succeed and register correctly.** `joule get ahf_finance_assistant_capability`
   confirms deployed version `1.0.0` matches the design-time version, with 1 system alias
   registered. We also did a full hard-reset (`joule remove` then a fresh `joule deploy`) to rule
   out any stale registration — the failure persisted identically afterward.

6. **A separate, likely-related platform issue was also observed**: for a period during this
   investigation, *every* `joule deploy` in this tenant — including redeploying the unmodified,
   known-working `ap_inquiry_agent_a2a` capability — failed with:
   ```
   Failed to fetch system aliases from the configuration repository.
   Please try again later. (code: Tenant Administration - 3001)
   ```
   This confirmed a tenant-wide deploy-pipeline degradation at the time (correlation IDs
   `bdfeabbf-e706-4e8a-499c-d28a808c83ec`, `4acb6aac-ea6d-4ee2-64e5-9b9791e475cf`,
   `f6c43252-2755-46c8-4954-ba9ebfec90b7`, `5eab0e5e-f216-4e40-699a-4f98fd43b2dd`). Deploys have
   since started succeeding again, but the `JCore-4004` runtime failure above persists
   unchanged, so we don't believe the two are fully explained by the same root cause.

## What we need from SAP
Since the failure is entirely server-side with no diagnostic detail exposed to the client, we
need SAP to trace the `PROCESSING_FAILED` event server-side using the log_id/correlation_id
values above to find the actual underlying exception behind the generic `JCore-4004` wrapper.

## Business impact
This blocks a customer-facing Joule chat integration for a finance assistant agent that is
otherwise fully built, tested, and working end-to-end via direct API access.
