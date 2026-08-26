"""Environment-driven configuration.

All values come from environment variables (or a local .env for dev) so that
Cloud Foundry service bindings and env-specific config (step 7) can be wired
in later without touching code. Nothing here is a secret - secrets arrive via
Cloud Foundry service bindings once the Generative AI Hub / HANA Cloud /
Integration Suite steps are wired in.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from ahf_agent import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "dev"  # dev | test | prod
    service_name: str = "ahf-finance-assistant"
    service_version: str = __version__
    log_level: str = "INFO"
    port: int = 8080

    # Externally reachable base URL of this agent (used in the A2A agent
    # card). Locally this is http://localhost:<port>; in Cloud Foundry this
    # is the app's route.
    agent_base_url: str = "http://localhost:8080"

    # SAP Generative AI Hub connectivity (step 2). This subaccount has no
    # directly bindable `aicore` marketplace service, so AI Core is reached
    # through a BTP destination (resolved at call time via the bound
    # `destination-service` instance - see ahf_agent.ai_core) rather than a
    # service key baked in here. Defaults point at the GENAICORE destination
    # and GPT 5.2 deployment already live in this subaccount.
    model_name: str = "gpt-5.2"
    ai_core_destination_name: str = "GENAICORE"
    ai_core_resource_group: str = "default"
    llm_deployment_id: str = "dcc9a836b894dc1d"

    # S/4HANA OData connectivity (step 4), also via a BTP destination -
    # see ahf_agent.s4hana. Read-only: never used for write-back.
    s4hana_destination_name: str = "S43"


@lru_cache
def get_settings() -> Settings:
    return Settings()
