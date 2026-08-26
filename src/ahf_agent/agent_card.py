"""Builds this agent's A2A Agent Card - the document Joule (the A2A client)
uses for capability discovery when it's registered via the IAS App2App trust
(configured separately by an SAP admin; see README).

The skills below describe the target scope end-to-end so Joule can route the
right questions here from day one. The underlying answering logic is still a
placeholder until the RAG pipeline (step 3) and MCP Gateway tools (step 4)
are wired in - see ahf_agent.executor.
"""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import DEFAULT_RPC_URL, TransportProtocol

from ahf_agent.config import Settings

_POLICY_FAQ_SKILL = AgentSkill(
    id="finance_policy_faq",
    name="Finance & procurement policy Q&A",
    description=(
        "Answers routine AP, procurement, and general finance questions (e.g. "
        "T&E policy, PO approval thresholds, vendor onboarding steps) grounded "
        "in company SOP and policy documents, and links to the source document "
        "on the shared drive. Escalates to a human queue when not confident."
    ),
    tags=["finance", "accounts-payable", "procurement", "policy", "faq"],
    examples=[
        "What is our T&E policy for international travel?",
        "What is the approval threshold for a PO over $50,000?",
        "What documents do I need to onboard a new vendor?",
    ],
)

_S4HANA_STATUS_SKILL = AgentSkill(
    id="s4hana_status_lookup",
    name="Read-only S4HANA status lookup",
    description=(
        "Looks up read-only status for invoices, purchase orders, purchase "
        "requisitions, vendor master records, and posted payments in S4HANA. "
        "Never performs write-back or transactional actions, and never returns "
        "PII or vendor banking data."
    ),
    tags=["finance", "s4hana", "invoice", "purchase-order", "vendor", "payment"],
    examples=[
        "What is the status of invoice 1900000123?",
        "Has payment posted against PO 4500001234?",
        "Is vendor 100234 fully onboarded?",
    ],
)


def build_agent_card(settings: Settings) -> AgentCard:
    return AgentCard(
        name="AHF Finance Assistant",
        description=(
            "Answers routine accounts payable, procurement, and general finance "
            "questions, grounds every answer in company policy documents, and "
            "escalates to a human when it isn't confident. Read-only: makes no "
            "write-back or transactional changes in S4HANA."
        ),
        version=settings.service_version,
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[_POLICY_FAQ_SKILL, _S4HANA_STATUS_SKILL],
        supported_interfaces=[
            AgentInterface(
                url=f"{settings.agent_base_url}{DEFAULT_RPC_URL}",
                protocol_binding=TransportProtocol.JSONRPC,
            )
        ],
    )
