"""IPRoyal sticky-session proxy helper. get_sticky_session() hands out a fresh
rotating session id each call; proxy_healthy() verifies egress works."""
import itertools
from dataclasses import dataclass

import httpx

from config import get_config

_counter = itertools.count(1)


@dataclass
class ProxySession:
    id: str
    url: str  # full http://user:pass@host:port, or "" when no proxy configured


def get_sticky_session() -> ProxySession:
    cfg = get_config()
    sid = f"session-{next(_counter)}"
    if not cfg.iproyal_proxy:
        return ProxySession(id=sid, url="")  # dev / no-proxy mode
    user = cfg.iproyal_user
    if user:
        user = f"{user}-{sid}"  # IPRoyal sticky-session suffix
    auth = ""
    if user:
        auth = f"{user}:{cfg.iproyal_pass}@" if cfg.iproyal_pass else f"{user}@"
    return ProxySession(id=sid, url=f"http://{auth}{cfg.iproyal_proxy}")


def proxy_healthy() -> bool:
    cfg = get_config()
    if not cfg.iproyal_proxy:
        return False
    try:
        session = get_sticky_session()
        with httpx.Client(proxy=session.url, timeout=10) as client:
            return client.get("https://api.ipify.org?format=json").status_code == 200
    except Exception:
        return False
