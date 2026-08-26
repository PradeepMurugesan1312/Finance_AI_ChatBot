# Build Prompt — AI Chatbot for Routine Finance Questions (Full Production Build)

Paste this into Claude inside SAP BTP Business Application Studio (BAS) to kick off the build.

---

## Context

You are helping me build a **production-grade AI chatbot** for a finance organization (internal codename: AHF). The chatbot answers routine finance questions — invoice status, T&E policy, PO approval thresholds, vendor onboarding — grounds every answer in company documents, and escalates to a human when it isn't confident. It must NOT perform any write-back or transactional action in S4HANA.

This is being built on SAP's native AI stack, not a bespoke external chatbot, because S4HANA is already the system of record and this approach inherits SAP's existing auth/roles and cuts integration work.

Treat this as a real production system: proper error handling, structured logging, secrets management, retries/timeouts, and tests — not a proof-of-concept script.

## Scope

**In scope:**
- Accounts payable, procurement, and general finance FAQs
- Document lookup and linking to the correct shared-drive document
- Read-only S4HANA status checks (e.g., invoice/payment status, PO status)
- Escalation to a human queue when confidence is low

**Out of scope — do not build any of this:**
- Any write-back to S4HANA (no bot-initiated approvals or payments)
- Multi-turn financial analysis
- Non-finance questions
- Anything that returns PII or vendor banking data in a response

## Target Architecture

Build a **custom, code-based agent implementing the A2A (Agent2Agent) protocol as an A2A server**, in BAS, deployed to Cloud Foundry. This gives full pro-code control over the logic while still plugging into SAP's ecosystem:

1. **A2A Server (this repo)** — the core agent, built in BAS, deployed to Cloud Foundry.
2. **Joule as the A2A client** — connects to this agent through a Joule Scenario and Dialog Function, secured by an Identity Authentication Service (IAS) App2App trust relationship. Employees reach the bot through the same Joule chat surface inside Teams and S4HANA.
3. **SAP Generative AI Hub on SAP AI Core** — the model and grounding layer.
   - Answering model: **GPT 5.2**, deployed through Generative AI Hub (reuse the same deployment pattern already proven on the "van" project — ask me for those deployment details if you need them).
   - Embedding model: a lightweight option such as **text-embedding-3-small**, used only to index the knowledge base. Embeddings do not need to match the answering model.
4. **HANA Cloud vector store** — holds the embedded knowledge base so it stays inside SAP's data estate.
5. **Knowledge base** — built from existing AP, procurement, and finance SOPs and policy documents from the shared drive (assume SharePoint unless told otherwise — the connector should be swappable without changing the architecture).
6. **SAP Integration Suite's MCP Gateway** — exposes S4HANA APIs to the agent as governed, business-level tools (e.g., a `check_invoice_status` tool), never as raw endpoint passthrough.

### Required S4HANA APIs (expose each as an MCP Gateway tool, not a raw call)

| API | Purpose | Suggested tool name |
|---|---|---|
| `API_SUPPLIERINVOICE_PROCESS_SRV` | AP — invoice status, payment terms, PO matching | `check_invoice_status` |
| `API_PURCHASEORDER_PROCESS_SRV` | Procurement — PO status and approval details | `check_po_status` |
| `API_PURCHASEREQ_PROCESS_SRV` | Procurement — purchase requisition status | `check_pr_status` |
| `API_BUSINESS_PARTNER` | Vendor master data — onboarding/setup status | `check_vendor_status` |
| `API_OPLACCTGDOCITEMCUBE_SRV` | Finance — confirms whether payment has posted against an invoice | `check_payment_posted` |

## Build Order (please follow this sequence)

1. **Scaffold the A2A server** in BAS: project structure, dependency setup, health check endpoint, and A2A protocol compliance (agent card / capabilities discovery, task lifecycle, synchronous request handling).
2. **Wire in the GPT 5.2 deployment** through SAP Generative AI Hub for answer generation.
3. **Build the RAG pipeline**: document ingestion/chunking → embed with text-embedding-3-small → load into the HANA Cloud vector store → retrieval at query time → pass retrieved context into the GPT 5.2 prompt with strict grounding instructions (answer only from retrieved context; if not found, say so and offer escalation).
4. **Add the MCP Gateway tool calls** for the five S4HANA APIs above once they're exposed as tools — implement them as callable tools the agent can invoke mid-conversation, with proper auth headers and timeout handling.
5. **Handle latency correctly**: synchronous A2A calls get a 60-second budget. Any lookup that risks running longer must use the async webhook pattern Joule supports instead of forcing it through the synchronous path. Build both paths.
6. **Escalation logic**: define and implement a clear, low confidence bar for handing off to a human queue rather than guessing.
7. **Deploy to Cloud Foundry**, with environment-specific config (dev/test/prod), secrets via Cloud Foundry service bindings (never hardcoded), and structured logs.
8. **Observability**: instrument the service so SAP AI Core's inference observability can be turned on from day one to catch grounding failures early (log prompts, retrieved context, and responses in a way that supports this).
9. **Tests**: unit tests for the RAG retrieval logic and each MCP tool wrapper; integration test(s) that simulate a full A2A round trip end to end.

## Security & Governance Requirements

- Access must follow existing S4HANA roles, inherited through the agent's own service credentials — do not invent a separate auth scheme.
- Never include PII or vendor banking data in a chatbot response, even if the underlying API returns it — filter/redact before responding.
- Assume the IAS App2App trust relationship between Joule and this agent server is configured separately (requires SAP admin access) — your job is to make the agent's endpoint ready to be registered, not to configure IAS yourself unless I say otherwise.
- No write operations to S4HANA under any circumstance, even if a tool technically supports it.

## What I want from you right now

Start with step 1 (scaffold the A2A server). Before writing code:
- Propose the project structure and the tech stack you'd use inside BAS for the A2A server (language/framework), and confirm it against what's typically supported for SAP Cloud Foundry deployment.
- Ask me for anything you need that isn't in this prompt (e.g., existing Generative AI Hub deployment details from the "van" project, SharePoint vs. actual shared-drive platform, Cloud Foundry org/space details) rather than assuming.
- Then scaffold the repo and implement step 1 fully, production-quality, with tests.

Work through the remaining steps one at a time, confirming with me before moving to the next, rather than generating the entire system in one pass.
