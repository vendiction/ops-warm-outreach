"""Central config for the audit worker. Reads env; no side effects at import."""
import os
from functools import lru_cache


class Config:
    def __init__(self) -> None:
        # DB
        self.database_url = os.getenv("DATABASE_URL", "")
        # Anthropic
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.gap_summary_model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-6")
        # Disposable inbox pool
        self.protonmail_pool_file = os.getenv("PROTONMAIL_POOL_FILE", "./secrets/protonmail_pool.json")
        self.inbox_max_per_week = int(os.getenv("INBOX_MAX_PER_WEEK", "5"))
        self.inbox_cooldown_hours = int(os.getenv("INBOX_COOLDOWN_HOURS", "48"))
        self.inbox_state_file = os.getenv("INBOX_STATE_FILE", "/data/inbox_state.json")
        # Proxies (IPRoyal)
        self.iproyal_proxy = os.getenv("IPROYAL_PROXY", "")           # host:port
        self.iproyal_user = os.getenv("IPROYAL_PROXY_USER", "")
        self.iproyal_pass = os.getenv("IPROYAL_PROXY_PASS", "")
        # Playwright / audit behavior
        self.headless = os.getenv("AUDIT_HEADLESS", "true").lower() != "false"
        self.nav_timeout_ms = int(os.getenv("AUDIT_NAV_TIMEOUT_MS", "30000"))


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()
