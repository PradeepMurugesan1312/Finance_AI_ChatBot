from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH


def test_agent_card_is_discoverable(client):
    response = client.get(AGENT_CARD_WELL_KNOWN_PATH)

    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "AHF Finance Assistant"
    assert len(card["skills"]) >= 1
    assert {skill["id"] for skill in card["skills"]} == {
        "finance_policy_faq",
        "s4hana_status_lookup",
    }


def test_agent_card_declares_no_streaming_or_push_yet(client):
    response = client.get(AGENT_CARD_WELL_KNOWN_PATH)
    card = response.json()

    # Streaming and push-notification (async webhook) support land in step 5;
    # the agent card must not overclaim capabilities that aren't wired up yet.
    assert card["capabilities"]["streaming"] is False
    assert card["capabilities"]["pushNotifications"] is False


def test_agent_card_advertises_jsonrpc_endpoint(client):
    response = client.get(AGENT_CARD_WELL_KNOWN_PATH)
    card = response.json()

    interfaces = card["supportedInterfaces"]
    assert any(
        interface["protocolBinding"] == "JSONRPC"
        and interface["url"] == "http://testserver/"
        for interface in interfaces
    )
