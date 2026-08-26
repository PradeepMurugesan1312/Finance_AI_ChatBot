"""Resolve BTP destinations via the Destination service.

Shared by ahf_agent.ai_core (the "GENAICORE" destination, for SAP Generative
AI Hub) and ahf_agent.s4hana (the "S43" destination, for S/4HANA OData APIs).
In Cloud Foundry, the Destination service is bound to this app as the
"destination-service" instance (see manifest.yml). At runtime we
authenticate to the Destination service with its own OAuth2
client-credentials, then ask it to resolve a named destination into a target
URL plus ready-to-use auth headers.

This subaccount's destination service has a known issue auto-fetching tokens
for OAuth2ClientCredentials destinations (the resolved auth token comes back
with a CSRF error instead of a bearer token, even though the destination
itself is configured correctly). When that happens, this module falls back
to doing the client-credentials exchange itself, using the raw
clientId/clientSecret/tokenServiceURL the destination service still returns
in destinationConfiguration for exactly this purpose.
"""

from __future__ import annotations

import json
import os
import time

import httpx

from ahf_agent.logging_config import get_logger

logger = get_logger(__name__)

# Cache the destination-service's own OAuth token (not the target system's) -
# it's reused across requests until close to expiry.
_token_cache: dict[str, tuple[str, float]] = {}


class DestinationError(RuntimeError):
    """Raised when a BTP destination cannot be resolved or is misconfigured."""


def _destination_service_credentials() -> dict:
    vcap_raw = os.environ.get("VCAP_SERVICES")
    if not vcap_raw:
        raise DestinationError(
            "VCAP_SERVICES is not set - no destination-service binding found "
            "(only present when running on Cloud Foundry; see manifest.yml's "
            "`services:` list)"
        )
    vcap = json.loads(vcap_raw)
    for entry in vcap.get("destination", []):
        return entry["credentials"]
    raise DestinationError("No 'destination' service instance is bound to this app")


async def _destination_service_token(client: httpx.AsyncClient, creds: dict) -> str:
    cache_key = creds["clientid"]
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    resp = await client.post(
        f"{creds['url']}/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(creds["clientid"], creds["clientsecret"]),
        timeout=10.0,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    _token_cache[cache_key] = (token, time.monotonic() + body.get("expires_in", 3600) - 60)
    return token


async def _manual_client_credentials_exchange(
    client: httpx.AsyncClient, dest_config: dict
) -> str | None:
    """Fallback when the destination service's own token auto-fetch fails.

    destinationConfiguration still carries the raw clientId/clientSecret/
    tokenServiceURL for OAuth2ClientCredentials destinations even when the
    auto-fetch itself errors, so we can do the exchange ourselves.
    """
    client_id = dest_config.get("clientId")
    client_secret = dest_config.get("clientSecret")
    token_url = dest_config.get("tokenServiceURL")
    if not (client_id and client_secret and token_url):
        return None

    resp = await client.post(
        f"{token_url}/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _connectivity_service_credentials() -> dict:
    vcap_raw = os.environ.get("VCAP_SERVICES")
    if not vcap_raw:
        raise DestinationError("VCAP_SERVICES is not set - no connectivity service binding found")
    vcap = json.loads(vcap_raw)
    for entry in vcap.get("connectivity", []):
        return entry["credentials"]
    raise DestinationError(
        "No 'connectivity' service instance is bound to this app (required for "
        "OnPremise destinations, routed through the Cloud Connector)"
    )


async def _connectivity_proxy(client: httpx.AsyncClient) -> dict:
    """Resolve the Cloud Connector on-premise proxy address and its access token.

    The connectivity service's own OAuth2 client credentials authenticate this
    app to the on-premise proxy - separate from, and in addition to, whatever
    auth the destination itself uses against the backend system.
    """
    creds = _connectivity_service_credentials()
    cache_key = f"connectivity:{creds['clientid']}"
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.monotonic():
        token = cached[0]
    else:
        resp = await client.post(
            f"{creds['token_service_url']}/oauth/token",
            data={"grant_type": "client_credentials"},
            auth=(creds["clientid"], creds["clientsecret"]),
            timeout=10.0,
        )
        resp.raise_for_status()
        body = resp.json()
        token = body["access_token"]
        _token_cache[cache_key] = (token, time.monotonic() + body.get("expires_in", 3600) - 60)

    return {
        "url": f"http://{creds['onpremise_proxy_host']}:{creds['onpremise_proxy_port']}",
        "headers": {"Proxy-Authorization": f"Bearer {token}"},
    }


async def resolve_destination(client: httpx.AsyncClient, name: str) -> dict:
    """Resolve a BTP destination by name into a base URL, auth headers, and
    (for OnPremise destinations) a forward proxy to route the request through.

    Returns {"url": ..., "headers": ..., "proxy": {"url": ..., "headers": ...} | None}.
    Callers must route the request through "proxy" (as an HTTP forward proxy)
    when it is not None.
    """
    creds = _destination_service_credentials()
    own_token = await _destination_service_token(client, creds)

    resp = await client.get(
        f"{creds['uri']}/destination-configuration/v1/destinations/{name}",
        headers={"Authorization": f"Bearer {own_token}", "Accept": "application/json"},
        timeout=10.0,
    )
    if resp.status_code == 404:
        raise DestinationError(
            f"Destination {name!r} does not exist in this subaccount - create "
            "it in BTP Cockpit (Connectivity -> Destinations) first."
        )
    resp.raise_for_status()
    body = resp.json()

    dest_config = body["destinationConfiguration"]
    base_url = dest_config["URL"].rstrip("/")

    proxy = None
    if dest_config.get("ProxyType") == "OnPremise":
        if dest_config.get("Authentication") == "PrincipalPropagation":
            raise DestinationError(
                f"Destination {name!r} uses Authentication=PrincipalPropagation over "
                "Cloud Connector, which requires an authenticated end-user identity "
                "to propagate. This agent's A2A endpoint is currently unauthenticated, "
                "so there is no user identity to propagate."
            )
        proxy = await _connectivity_proxy(client)

    headers: dict[str, str] = {}
    for auth_token in body.get("authTokens", []):
        http_header = auth_token.get("http_header")
        if http_header:
            headers[http_header["key"]] = http_header["value"]
            break

    if "Authorization" not in headers and dest_config.get("Authentication") == "OAuth2ClientCredentials":
        access_token = await _manual_client_credentials_exchange(client, dest_config)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

    if "Authorization" not in headers and dest_config.get("Authentication") not in (
        "NoAuthentication",
        None,
    ):
        raise DestinationError(
            f"Destination {name!r} did not yield a usable auth header "
            f"(Authentication={dest_config.get('Authentication')!r})"
        )

    return {"url": base_url, "headers": headers, "proxy": proxy}
