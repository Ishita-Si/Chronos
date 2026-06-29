"""
CHRONOS application server.

A zero-dependency HTTP server (Python standard library) exposing the REST API
and serving the mobile-first frontend. A production deployment would swap this
for FastAPI/uvicorn behind RBAC + audit middleware; the route contract is
identical.

Run:  python -m chronos.server
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import config, security
from .pipeline import ensure_built
from .store import db
from .ingest import pid as pid_parser
from .intel import vectorstore, copilot, sequence, rca, compliance, graph
from .eval import benchmark

_STORE: vectorstore.VectorStore | None = None
_ctx = threading.local()   # holds the resolved role per request
_STATIC = {"/": "index.html", "/index.html": "index.html",
           "/app.js": "app.js", "/styles.css": "styles.css"}
_CTYPE = {"html": "text/html", "js": "application/javascript",
          "css": "text/css", "json": "application/json"}


def _store() -> vectorstore.VectorStore:
    global _STORE
    if _STORE is None:
        conn = db.connect()
        _STORE = vectorstore.build_store(conn)
        conn.close()
    return _STORE


# --- API route handlers (each returns a JSON-serialisable object) -----------

def api_health(conn, q, body):
    return {"status": "ok", "as_of": config.AS_OF, "version": "1.0.0"}


def api_stats(conn, q, body):
    def n(t):
        return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    trajs = sequence.discover_trajectories(conn)
    fleet = sequence.fleet_risk(conn)
    comp = compliance.report(conn)
    return {
        "events": n("events"), "passages": n("passages"),
        "documents": n("documents"), "assets": n("assets"),
        "edges": n("edges"), "clauses": n("clauses"),
        "trajectories": len(trajs),
        "assets_at_risk": len(fleet),
        "compliance_rate": comp["summary"]["compliance_rate"],
        "open_gaps": len(comp["gaps"]),
    }


def api_assets(conn, q, body):
    out = []
    for a in graph.list_assets(conn):
        r = sequence.detect(conn, a["asset_id"])
        a = dict(a)
        a["at_risk"] = r.get("at_risk", False)
        a["risk_confidence"] = r.get("confidence", 0.0)
        out.append(a)
    return {"assets": out}


def api_asset(conn, q, body, asset_id):
    asset = graph.get_asset(conn, asset_id)
    if not asset:
        return {"error": "not found"}, 404
    timeline = [e for e in graph.asset_events(conn, asset_id)
                if e["subtype"] in config.SIGNIFICANT_SUBTYPES]
    return {
        "asset": asset,
        "timeline": timeline,
        "risk": sequence.detect(conn, asset_id),
        "governing_documents": graph.governing_documents(conn, asset_id),
        "clauses": graph.applicable_clauses(conn, asset_id),
        "connected_assets": graph.connected_assets(conn, asset_id),
    }


def api_timeseries(conn, q, body, asset_id):
    param = (q.get("param") or ["vibration"])[0]
    rows = db.query(conn,
        "SELECT ts, value, unit FROM events WHERE asset_id=? AND etype='READING' "
        "AND param=? ORDER BY ts", (asset_id, param))
    return {"asset_id": asset_id, "param": param, "points": rows}


def api_copilot(conn, q, body):
    question = (body or {}).get("question", "").strip()
    asset_id = (body or {}).get("asset_id") or None
    if not question:
        return {"error": "question required"}, 400
    return copilot.answer(conn, _store(), question, asset_id)


def api_risk(conn, q, body):
    return {"as_of": config.AS_OF, "fleet": sequence.fleet_risk(conn)}


def api_risk_asset(conn, q, body, asset_id):
    return sequence.detect(conn, asset_id)


def api_simulate(conn, q, body, asset_id):
    defer = float((q.get("defer") or ["7"])[0])
    return sequence.simulate(conn, asset_id, defer_days=defer)


def api_rca(conn, q, body, asset_id):
    return rca.rca(conn, asset_id)


def api_trajectories(conn, q, body):
    return {"trajectories": sequence.discover_trajectories(conn)}


def api_compliance(conn, q, body):
    asset_id = (q.get("asset_id") or [None])[0]
    standard = (q.get("standard") or [None])[0]
    return compliance.report(conn, asset_id=asset_id, standard=standard)


def api_compliance_pack(conn, q, body):
    clause_id = (q.get("clause_id") or [None])[0]
    asset_id = (q.get("asset_id") or [None])[0]
    if not clause_id or not asset_id:
        return {"error": "clause_id and asset_id required"}, 400
    return compliance.evidence_pack(conn, clause_id, asset_id)


def api_pid_list(conn, q, body):
    docs = pid_parser.read_pids()
    return {"pids": [{"doc_id": d["doc_id"], "path": d["path"],
                      "nodes": d["nodes"], "connections": d["connections"]}
                     for d in docs]}


def api_pid(conn, q, body, doc_id):
    for d in pid_parser.read_pids():
        if d["doc_id"] == doc_id:
            return d
    return {"error": "not found"}, 404


def api_benchmark(conn, q, body):
    return benchmark.run_all()


def api_audit(conn, q, body):
    limit = int((q.get("limit") or ["50"])[0])
    return {"entries": security.read_audit(limit), "count": security.audit_count()}


def api_whoami(conn, q, body):
    role = getattr(_ctx, "role", security.DEFAULT_ROLE)
    return {"role": role, "permissions": security.permissions(role),
            "roles": list(security.ROLE_SCOPES.keys())}


def api_document(conn, q, body, doc_id):
    doc = db.one(conn, "SELECT * FROM documents WHERE doc_id=?", (doc_id,))
    return doc or ({"error": "not found"}, 404)


def api_event(conn, q, body, event_id):
    ev = db.one(conn, "SELECT * FROM events WHERE event_id=?", (event_id,))
    return ev or ({"error": "not found"}, 404)


# Route table: (method, compiled_regex, handler)
ROUTES = [
    ("GET", r"/api/health$", api_health),
    ("GET", r"/api/stats$", api_stats),
    ("GET", r"/api/assets$", api_assets),
    ("GET", r"/api/asset/([\w\-]+)$", api_asset),
    ("GET", r"/api/timeseries/([\w\-]+)$", api_timeseries),
    ("POST", r"/api/copilot$", api_copilot),
    ("GET", r"/api/risk$", api_risk),
    ("GET", r"/api/risk/([\w\-]+)$", api_risk_asset),
    ("GET", r"/api/simulate/([\w\-]+)$", api_simulate),
    ("GET", r"/api/rca/([\w\-]+)$", api_rca),
    ("GET", r"/api/trajectories$", api_trajectories),
    ("GET", r"/api/compliance$", api_compliance),
    ("GET", r"/api/compliance/pack$", api_compliance_pack),
    ("GET", r"/api/pid$", api_pid_list),
    ("GET", r"/api/pid/([\w\-]+)$", api_pid),
    ("GET", r"/api/benchmark$", api_benchmark),
    ("GET", r"/api/audit$", api_audit),
    ("GET", r"/api/whoami$", api_whoami),
    ("GET", r"/api/document/([\w\-]+)$", api_document),
    ("GET", r"/api/event/([\w\-]+)$", api_event),
]
ROUTES = [(m, re.compile(p), h) for m, p, h in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "CHRONOS/1.0"

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send_json(self, obj, status=200):
        payload = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, name):
        path = config.FRONTEND_DIR / name
        if not path.exists():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ext = name.rsplit(".", 1)[-1]
        self.send_response(200)
        self.send_header("Content-Type", _CTYPE.get(ext, "text/plain") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # never cache the SPA shell/assets, so redeploys reflect immediately
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path, q = parsed.path, parse_qs(parsed.query)

        if method == "GET" and path in _STATIC:
            return self._send_static(_STATIC[path])

        # --- RBAC: resolve role, authorise against the route's scope ---
        token = self.headers.get("X-CHRONOS-Token")
        role = security.role_for(token, (q.get("role") or [None])[0])
        _ctx.role = role
        scope = security.scope_for(path)
        if path.startswith("/api/") and not security.can(role, scope):
            security.audit(role, method, path, 403)
            return self._send_json(
                {"error": f"role '{role}' lacks '{scope}' permission", "role": role,
                 "required_scope": scope}, 403)

        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return self._send_json({"error": "invalid JSON"}, 400)

        for m, rx, handler in ROUTES:
            if m != method:
                continue
            match = rx.match(path)
            if not match:
                continue
            conn = db.connect()
            try:
                result = handler(conn, q, body, *match.groups())
            except Exception as exc:  # surface errors as JSON, keep server up
                conn.close()
                security.audit(role, method, path, 500)
                return self._send_json({"error": str(exc)}, 500)
            conn.close()
            if isinstance(result, tuple):
                obj, status = result
                security.audit(role, method, path, status)
                return self._send_json(obj, status)
            security.audit(role, method, path, 200)
            return self._send_json(result)

        security.audit(role, method, path, 404)
        self._send_json({"error": f"no route for {method} {path}"}, 404)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


def main() -> None:
    ensure_built()
    _store()  # warm the vector index
    addr = (config.HOST, config.PORT)
    httpd = ThreadingHTTPServer(addr, Handler)
    print(f"CHRONOS — Unread Plant Memory Engine")
    print(f"  Serving on http://{config.HOST}:{config.PORT}")
    print(f"  API health: http://{config.HOST}:{config.PORT}/api/health")
    print("  Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
