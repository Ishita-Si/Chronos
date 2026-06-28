"""
Security: role-based access control (RBAC) + append-only audit trail.

A deliberately small, transparent implementation suitable for an on-prem /
air-gapped plant deployment. Tokens map to roles; roles grant scopes; every API
call is authorised against the route's scope and written to an immutable audit
log. Production would back this with the plant IdP (LDAP/SAML) and a tamper-
evident store — the contract here is identical.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from . import config

DEFAULT_ROLE = "engineer"

# demo tokens -> role (X-CHRONOS-Token header or ?role= query param)
TOKENS = {
    "tech-demo": "technician",
    "eng-demo": "engineer",
    "comp-demo": "compliance",
    "admin-demo": "admin",
}

# role -> granted scopes
ROLE_SCOPES = {
    "technician": {"read", "copilot", "rca"},
    "engineer":   {"read", "copilot", "rca", "simulate", "benchmark", "compliance"},
    "compliance": {"read", "copilot", "compliance"},
    "admin":      {"read", "copilot", "rca", "simulate", "benchmark", "compliance", "audit"},
}

# path -> required scope (first match wins)
_SCOPE_RULES = [
    (re.compile(r"/api/copilot"), "copilot"),
    (re.compile(r"/api/simulate"), "simulate"),
    (re.compile(r"/api/rca"), "rca"),
    (re.compile(r"/api/benchmark"), "benchmark"),
    (re.compile(r"/api/compliance"), "compliance"),
    (re.compile(r"/api/audit"), "audit"),
    (re.compile(r"/api/"), "read"),
]

_AUDIT_PATH = config.VAR_DIR / "audit.log"


def role_for(token: str | None, query_role: str | None) -> str:
    if token and token in TOKENS:
        return TOKENS[token]
    if query_role and query_role in ROLE_SCOPES:
        return query_role
    return DEFAULT_ROLE


def scope_for(path: str) -> str:
    for rx, scope in _SCOPE_RULES:
        if rx.match(path):
            return scope
    return "read"


def can(role: str, scope: str) -> bool:
    return scope in ROLE_SCOPES.get(role, set())


def permissions(role: str) -> list[str]:
    return sorted(ROLE_SCOPES.get(role, set()))


def audit(role: str, method: str, path: str, status: int) -> None:
    config.ensure_dirs()
    entry = {"ts": datetime.utcnow().isoformat(timespec="seconds"),
             "role": role, "method": method, "path": path, "status": status}
    with _AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit(limit: int = 50) -> list[dict]:
    if not _AUDIT_PATH.exists():
        return []
    lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def audit_count() -> int:
    if not _AUDIT_PATH.exists():
        return 0
    return sum(1 for _ in _AUDIT_PATH.open(encoding="utf-8"))
