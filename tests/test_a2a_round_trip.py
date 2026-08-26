"""Simulates a full A2A round trip end to end, in the two shapes this agent
needs to support:

- `test_full_round_trip_as_joule_sends_it`: Joule's A2A client currently
  speaks the older v0.3 JSON-RPC method names (`message/send`), and its
  default Dialog Function template extracts the reply via
  `apiResponse.body.artifacts[0].parts[0].text` - see SAP's Joule/A2A
  CodeJam (SAP-samples/codejam-code-based-agents). This is the request this
  agent must handle correctly to actually work once registered in Joule
  Studio.
- `test_full_round_trip_native_v1_0`: the v1.0-native method name
  (`SendMessage`), for any client built against the current A2A spec.
"""

import uuid

from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL


def test_agent_card_is_discoverable_before_any_task(client):
    response = client.get(AGENT_CARD_WELL_KNOWN_PATH)
    assert response.status_code == 200
    rpc_url = response.json()["supportedInterfaces"][0]["url"]
    assert rpc_url.endswith(DEFAULT_RPC_URL)


def test_full_round_trip_as_joule_sends_it(client):
    payload = {
        "jsonrpc": "2.0",
        "id": "joule-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": "What is our T&E policy for international travel?",
                    }
                ],
                "messageId": str(uuid.uuid4()),
                "kind": "message",
            }
        },
    }

    response = client.post(DEFAULT_RPC_URL, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body
    assert body["id"] == "joule-1"

    task = body["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["parts"][0]["text"]


def test_full_round_trip_native_v1_0(client):
    payload = {
        "jsonrpc": "2.0",
        "id": "v1-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "What is our T&E policy for international travel?"}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }

    response = client.post(
        DEFAULT_RPC_URL, json=payload, headers={"A2A-Version": "1.0"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body

    # Unlike the v0.3-compat response, the native v1.0 result wraps the task.
    task = body["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["artifacts"][0]["parts"][0]["text"]
