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
import base64
import hashlib
import hmac
from datetime import datetime

from . import config

DEFAULT_ROLE = "engineer"

# Demo users. These are deliberately non-secret credentials for the judging
# demo; production would delegate this contract to the plant IdP.
DEMO_USERS = {
    "tech": {"password": "tech-demo", "role": "technician", "name": "Technician"},
    "engineer": {"password": "eng-demo", "role": "engineer", "name": "Engineer"},
    "compliance": {"password": "comp-demo", "role": "compliance", "name": "Compliance Officer"},
    "admin": {"password": "admin-demo", "role": "admin", "name": "Admin"},
}

_JWT_SECRET = b"chronos-demo-jwt-secret"

# Legacy demo tokens -> role (X-CHRONOS-Token header or ?role= query param)
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
    if token:
        if token.startswith("Bearer "):
            token = token[7:].strip()
        jwt_role = _role_from_jwt(token)
        if jwt_role:
            return jwt_role
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


def demo_identities() -> list[dict]:
    """Return demo login metadata and signed JWTs for the role switcher."""
    out = []
    for user_id, meta in DEMO_USERS.items():
        role = meta["role"]
        out.append({
            "id": user_id,
            "password": meta["password"],
            "role": role,
            "name": meta["name"],
            "token": issue_demo_jwt(user_id, role),
            "permissions": permissions(role),
        })
    return out


def issue_demo_jwt(user_id: str, role: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "role": role, "iss": "chronos-demo", "aud": "chronos-ui"}
    signing_input = f"{_b64json(header)}.{_b64json(payload)}"
    sig = hmac.new(_JWT_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


def _role_from_jwt(token: str) -> str | None:
    try:
        head, payload, sig = token.split(".")
    except ValueError:
        return None
    signing_input = f"{head}.{payload}"
    expected = _b64(hmac.new(_JWT_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        claims = json.loads(_b64decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    role = claims.get("role")
    return role if role in ROLE_SCOPES else None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64json(obj: dict) -> str:
    return _b64(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


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
