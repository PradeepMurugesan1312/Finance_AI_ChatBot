"""Simulates what Joule (the A2A client) does on a real turn: discover the
agent card, then send a message over JSON-RPC and read back the synchronous
reply. This is the end-to-end round trip required by build step 9.
"""

import uuid

from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL


def test_full_a2a_round_trip(client):
    card_response = client.get(AGENT_CARD_WELL_KNOWN_PATH)
    assert card_response.status_code == 200
    rpc_url = card_response.json()["supportedInterfaces"][0]["url"]
    # The agent card advertises an absolute URL; the JSON-RPC route itself is
    # mounted at DEFAULT_RPC_URL on this same app.
    assert rpc_url.endswith(DEFAULT_RPC_URL)

    payload = {
        "jsonrpc": "2.0",
        "id": "round-trip-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "What is our T&E policy for international travel?"}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }

    send_response = client.post(
        DEFAULT_RPC_URL, json=payload, headers={"A2A-Version": "1.0"}
    )

    assert send_response.status_code == 200
    body = send_response.json()
    assert "error" not in body
    assert body["id"] == "round-trip-1"

    message = body["result"]["message"]
    assert message["role"] == "ROLE_AGENT"
    assert message["parts"][0]["text"]
    assert message["taskId"]
    assert message["contextId"]
