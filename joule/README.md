# Joule Studio capability

This folder is the Joule-side half of the integration: the YAML capability
that makes this A2A agent (in [`../src/ahf_agent`](../src/ahf_agent)) reachable
from the Joule chat surface. The agent code and this capability are deployed
and versioned separately - the agent to Cloud Foundry, this capability via
the Joule Studio CLI - but they only work together.

```
joule/
├── da.sapdas.yaml                              digital assistant manifest
└── ahf_finance_capability/
    ├── capability.sapdas.yaml                  metadata + system alias
    ├── scenarios/finance_faq_scenario.yaml      intent matching text
    └── functions/finance_faq_function.yaml      the agent-request call
```

## How it fits together

```
User asks a question in Joule chat
  -> finance_faq_scenario (intent match)
  -> finance_faq_function: agent-request action
  -> BTP Destination "AHF_FINANCE_AGENT_<ENV>"
  -> this agent's Cloud Foundry route
  -> GET /.well-known/agent-card.json (capability discovery)
  -> JSON-RPC message/send -> Task with an artifact
  -> function extracts apiResponse.body.artifacts[0].parts[0].text
  -> shown to the user as markdown
```

The `artifacts[0].parts[0].text` extraction path is why
[`ahf_agent/executor.py`](../src/ahf_agent/executor.py) responds with a
completed `Task` carrying an artifact, not a bare `Message` - that's the
shape Joule's function template reads.

## One-time setup per environment

1. **BTP Destination** (BTP Cockpit -> your subaccount -> Connectivity ->
   Destinations -> New Destination):
   - Name: `AHF_FINANCE_AGENT_<ENV>` (e.g. `AHF_FINANCE_AGENT_DEV`) - must
     match `system_aliases.AHF_FINANCE_AGENT.destination` in
     `ahf_finance_capability/capability.sapdas.yaml` exactly.
   - URL: this agent's Cloud Foundry route for that environment.
   - **Authentication: do not use `NoAuthentication`** the way SAP's public
     CodeJam sample does - that's fine for a training sandbox, not for a
     finance bot with S4HANA-scoped credentials. Per the project's security
     requirements, this destination must go through the IAS App2App trust
     relationship between Joule and this agent (OAuth2, `SAMLAssertion`, or
     the equivalent your SAP admin sets up) so access still inherits
     existing S4HANA roles - not a separate auth scheme. That trust/IAS
     setup is out of this repo's scope (see the main
     [README](../README.md) and the build prompt) and needs an SAP admin.
   - Update `capability.sapdas.yaml`'s destination name per environment
     (dev/test/prod) before deploying that environment's capability.

2. **Joule Studio CLI** (Node.js v20.12.0-v24 required):
   ```bash
   npm install -g @sap/joule-studio-cli
   joule login   # prompts for IAS tenant URL, Joule API URL, client id/secret, user
   ```

3. **Deploy the capability**:
   ```bash
   cd joule
   joule deploy -c -n "ahf_finance_assistant_dev"
   joule list                                  # confirm it deployed
   joule launch "ahf_finance_assistant_dev"    # opens a test chat client
   ```

## Troubleshooting

Same failure modes as SAP's own Joule/A2A CodeJam - if a message goes
unanswered or times out:

- `curl https://<this-agent-route>/healthz` and
  `curl https://<this-agent-route>/.well-known/agent-card.json` - confirm
  the agent is actually up and discoverable before suspecting the YAML.
- Destination name in the BTP cockpit must match `capability.sapdas.yaml`'s
  `system_aliases.AHF_FINANCE_AGENT.destination` exactly.
- Joule's synchronous budget is 60 seconds (see the main README and build
  step 5) - a slow S4HANA lookup once step 4 lands must go through the
  async webhook path instead of blocking this call.
- `joule lint` before `joule deploy` catches YAML schema errors early.

## References

- [SAP-samples/codejam-code-based-agents: Integrate Your Agent into SAP Joule](https://github.com/SAP-samples/codejam-code-based-agents/blob/main/exercises/Python-LangGraph/09-integrate-agent-into-joule.md) - the source for this folder's YAML shape (`agent-request`, `schema_version: 3.28.0`, the `artifacts[0].parts[0].text` SpEL path).
- [Joule A2A: Connect Code Based Agents into Joule (SAP Community)](https://community.sap.com/t5/technology-blog-posts-by-sap/joule-a2a-connect-code-based-agents-into-joule/ba-p/14329279)
- [Code-Based Agents (Bring Your Own Agent) - SAP Help Portal](https://help.sap.com/docs/joule/joule-development-guide-ba88d1ec6a1b442098863d577c19b0c0/code-based-agents-bring-your-own-agent)
- [SAP-samples/joule-a2a-agent-toolkit](https://github.com/SAP-samples/joule-a2a-agent-toolkit/) - a scaffolding CLI covering similar ground (TypeScript/Python + LangGraph); not used here since this repo already has its own scaffold, but worth a look for the Cloud Foundry manifest / Destination-provisioning pieces in step 7.

