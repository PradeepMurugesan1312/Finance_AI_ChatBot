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


@lru_cache
def get_settings() -> Settings:
    return Settings()
