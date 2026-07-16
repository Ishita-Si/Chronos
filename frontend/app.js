"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (x) => Math.round((x || 0) * 100);

let TOKEN = "eng-demo";
let AUTH_IDENTITIES = [];
let CURRENT_ID = "engineer";
async function api(path, opts = {}) {
  opts.headers = Object.assign({ "X-CHRONOS-Token": TOKEN }, opts.headers || {});
  const r = await fetch(path, opts);
  return r.json();
}
function denied(d) { return d && d.error && d.required_scope; }
function lock(d) {
  return `<div class="answer"><div class="conf-row"><span class="conf-badge conf-lo">🔒 Access denied</span></div>
    <p class="muted">Role <b>${esc(d.role)}</b> lacks the <b>${esc(d.required_scope)}</b> permission.
    Switch role (top right) to continue.</p></div>`;
}
function confClass(c) { return c >= 0.75 ? "conf-hi" : c >= 0.5 ? "conf-mid" : "conf-lo"; }

/* ---------------- navigation ---------------- */
$$("#tabs button").forEach(b => b.addEventListener("click", () => {
  $$("#tabs button").forEach(x => x.classList.remove("active"));
  $$(".view").forEach(v => v.classList.remove("active"));
  b.classList.add("active");
  $("#view-" + b.dataset.view).classList.add("active");
  updateContext(b.dataset.view);
  if (b.dataset.view === "risk") loadRiskTab();
  if (b.dataset.view === "compliance") loadCompliance();
  if (b.dataset.view === "pid") loadPID();
  if (b.dataset.view === "benchmark") loadBenchmark();
}));

/* plain-language context line under the tabs */
const VIEW_INFO = {
  dashboard: "<b>Overview</b> — the one thing that needs you right now, plus your plant by the numbers.",
  copilot: "<b>Ask</b> — type any question in plain English; CHRONOS answers with a confidence score and sources.",
  risk: "<b>Predictions</b> — every machine scored for how likely it is to fail, and roughly when.",
  pid: "<b>Equipment</b> — the plant map, read automatically from your P&ID engineering drawings.",
  compliance: "<b>Compliance</b> — which inspections are overdue, with audit-ready evidence in one click.",
  benchmark: "<b>Accuracy</b> — how well CHRONOS performs, measured against known correct answers.",
};
function updateContext(v) { const el = $("#view-context"); if (el) el.innerHTML = VIEW_INFO[v] || ""; }

/* role selector (RBAC) */
const roleSel = $("#role-select");
if (roleSel) roleSel.addEventListener("change", async () => {
  const next = AUTH_IDENTITIES.find(x => x.id === roleSel.value);
  if (!next) return;
  const ok = await requestRoleAuth(next);
  if (!ok) {
    roleSel.value = CURRENT_ID;
    return;
  }
  CURRENT_ID = next.id;
  TOKEN = next.token;
  await refreshForRole();
});

async function initAuthDemo() {
  const d = await api("/api/auth/demo");
  if (!d.identities || !roleSel) return;
  AUTH_IDENTITIES = d.identities;
  const preferred = AUTH_IDENTITIES.find(x => x.role === "engineer") || AUTH_IDENTITIES[0];
  roleSel.innerHTML = AUTH_IDENTITIES.map(x =>
    `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("");
  roleSel.value = preferred.id;
  CURRENT_ID = preferred.id;
  TOKEN = preferred.token;
}

async function refreshForRole() {
  const who = await api("/api/whoami");
  $("#asof").dataset.role = who.role;
  const active = $("#tabs button.active");
  if (active) active.click();        // re-render current view under new role
  loadDashboard();
}

function requestRoleAuth(identity) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "auth-overlay";
    overlay.innerHTML = `<div class="auth-card">
      <div class="ans-conf-label">Demo JWT authentication</div>
      <h3>Switch to ${esc(identity.name)}</h3>
      <p class="muted">Enter the demo ID and password from the README to mint this role's JWT.</p>
      <label>ID<input id="auth-id" autocomplete="username" value="${esc(identity.id)}"></label>
      <label>Password<input id="auth-pass" autocomplete="current-password" type="password" placeholder="${esc(identity.password)}"></label>
      <div id="auth-error" class="auth-error"></div>
      <div class="auth-actions">
        <button class="btn-ghost" id="auth-cancel">Cancel</button>
        <button class="btn-primary" id="auth-submit">Authenticate</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    const finish = (ok) => { overlay.remove(); resolve(ok); };
    $("#auth-cancel", overlay).onclick = () => finish(false);
    $("#auth-submit", overlay).onclick = () => {
      const id = $("#auth-id", overlay).value.trim();
      const pass = $("#auth-pass", overlay).value;
      if (id === identity.id && pass === identity.password) finish(true);
      else $("#auth-error", overlay).textContent = "ID or password does not match this demo role.";
    };
    $("#auth-pass", overlay).addEventListener("keydown", e => {
      if (e.key === "Enter") $("#auth-submit", overlay).click();
      if (e.key === "Escape") finish(false);
    });
    $("#auth-pass", overlay).focus();
  });
}

/* ---------------- dashboard ---------------- */
async function loadDashboard() {
  const h = await api("/api/health");
  $("#asof").innerHTML = `as of <b>${esc(h.as_of.slice(0, 10))}</b><br>v${esc(h.version)}`;

  const s = await api("/api/stats");
  const risk = await api("/api/risk");
  const n = risk.fleet.length;

  // 1) plain-language status banner
  $("#status-banner").innerHTML = n
    ? `<div class="banner warn"><span class="dot"></span>
         <div><b>${n} asset${n > 1 ? "s" : ""} need${n > 1 ? "" : "s"} attention.</b>
         Everything else is running normally.</div></div>`
    : `<div class="banner ok"><span class="dot"></span>
         <div><b>All assets healthy.</b> No failure patterns forming right now.</div></div>`;

  // 2) "needs attention now" — human, action-first hero card(s)
  $("#attention").innerHTML = n
    ? `<h2 class="section-title">Needs attention now</h2>` + risk.fleet.map(attentionCard).join("")
    : "";
  $$("#attention [data-ask]").forEach(b => b.addEventListener("click", e => {
    e.stopPropagation(); askFromHome(b.dataset.ask);
  }));
  $$("#attention [data-open]").forEach(b => b.addEventListener("click", e => {
    e.stopPropagation(); gotoAsset(b.dataset.open);
  }));

  // 3) quick actions
  $("#quick-actions").innerHTML = [
    qa("01", "Ask the plant brain", "Get a source-backed answer in seconds", "copilot"),
    qa("02", "Check what's at risk", "See assets trending toward failure", "risk"),
    qa("03", "Review compliance", "Find missing inspection evidence", "compliance"),
  ].join("");
  $$("#quick-actions .qa").forEach(c =>
    c.addEventListener("click", () => $(`[data-view="${c.dataset.go}"]`).click()));

  // 4) friendly "at a glance" metrics (plain language, no jargon)
  $("#glance").innerHTML = [
    kpi(s.assets, "Assets monitored"),
    kpi(s.documents + 1, "Knowledge sources"),
    kpi(n, n ? "Need attention" : "All healthy", n ? "alert" : "good"),
    kpi(pct(s.compliance_rate) + "%", `Compliance · ${s.open_gaps} gaps`,
        s.compliance_rate >= 0.8 ? "good" : "alert"),
  ].join("");

  // 5) technical detail, tucked away
  $("#kpis").innerHTML = [
    kpi(s.events.toLocaleString(), "Events linked"),
    kpi(s.edges.toLocaleString(), "Graph connections"),
    kpi(s.trajectories, "Failure patterns learned"),
    kpi(s.passages.toLocaleString(), "Searchable passages"),
  ].join("");

  animateKpis("#glance");
  animateKpis("#kpis");
}

const STAGE_LABEL = {
  seal_replacement: "after seal replacement", alignment_marginal: "alignment marginal",
  vibration_rise: "vibration rising", vibration_high: "high vibration",
  temporary_bypass: "safety bypass active", wo_deferred: "repair deferred",
  fouling_detected: "fouling detected", dp_high: "high differential pressure",
};
const humanStage = (s) => STAGE_LABEL[s] || (s || "").replace(/_/g, " ");

function attentionCard(r) {
  const d = Math.round(r.lead_time_days);
  const lead = r.lead_time_days == null ? "soon"
    : r.lead_time_days <= 0 ? "now — act immediately"
    : `in about ${d} ${d === 1 ? "day" : "days"}`;
  const cases = r.support || (r.similar_cases ? r.similar_cases.length : 0);
  return `<div class="attention-card">
    <div class="ac-head">
      <div><div class="ac-title">${esc(r.asset_id)} · ${esc(r.asset_name || "")}</div>
        <div class="ac-sub">currently at: ${esc(humanStage(r.current_stage))}</div></div>
      <span class="pill ${esc(r.criticality || "C")}">${esc(r.criticality || "")}</span>
    </div>
    <p class="ac-msg">This equipment is tracing a failure pattern that has ended in a
      trip <b>${cases} time${cases > 1 ? "s" : ""}</b> before on similar pumps. Its live
      signature now matches that pathway at <b>${pct(r.confidence)}% confidence</b> — at the
      current pace it could trip <b>${lead}</b>. Acting now breaks the chain.</p>
    ${heroWave()}
    <div class="ac-actions">
      <button class="btn-primary" data-ask="${esc(r.asset_id)}">See the recommended fix →</button>
      <button class="btn-ghost" data-open="${esc(r.asset_id)}">View timeline</button>
    </div>
  </div>`;
}

/* self-drawing vibration waveform: signal rising past the danger threshold */
function heroWave() {
  const W = 600, H = 66, N = 46, dangerY = 15;
  let d = "", area = "";
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const x = t * W;
    const base = 52 - t * t * 30;                 // drifts upward (worsening)
    const amp = 1.2 + t * t * 6.5;                // oscillation grows (chatter)
    const y = Math.max(6, base - amp * Math.sin(i * 0.9) - amp * 0.4 * Math.sin(i * 2.3));
    d += (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1) + " ";
    area += x.toFixed(1) + "," + y.toFixed(1) + " ";
  }
  return `<div class="ac-wave"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="wavefill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f7a932" stop-opacity=".30"/>
      <stop offset="100%" stop-color="#f7a932" stop-opacity="0"/></linearGradient></defs>
    <line class="danger" x1="0" y1="${dangerY}" x2="${W}" y2="${dangerY}"/>
    <text class="lbl" x="4" y="${dangerY - 3}">TRIP THRESHOLD</text>
    <polygon class="trace-fill" points="0,${H} ${area} ${W},${H}"/>
    <path class="trace" d="${d}"/>
    <circle class="pdot" cx="${W}" cy="6" r="3.5"/>
  </svg></div>`;
}

function skeleton(rows) {
  const lines = ["w80", "w60", "", "w40"];
  let h = `<div class="skel-wrap">`;
  for (let i = 0; i < (rows || 4); i++) h += `<div class="skel ${lines[i % lines.length]}"></div>`;
  return h + `</div>`;
}

const qa = (icon, title, sub, go) => `<div class="qa" data-go="${go}">
  <div class="qa-icon">${icon}</div><div class="qa-title">${esc(title)}</div>
  <div class="qa-sub">${esc(sub)}</div></div>`;

function askFromHome(assetId) {
  $('[data-view="copilot"]').click();
  $("#copilot-asset").value = assetId;
  $("#copilot-q").value = `What should I do about the failure pattern on ${assetId}?`;
  askCopilot();
}
function gotoAsset(id) {
  $('[data-view="risk"]').click();
  loadRiskTab().then(() => openAsset(id));
}

const kpi = (v, l, cls = "") => `<div class="kpi ${cls}"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`;

function trajCard(t) {
  const chain = t.pattern.map((p, i) => {
    const term = i === t.pattern.length - 1;
    return `<span class="stage ${term ? "term" : "hit"}">${esc(p.replace(/_/g, " "))}</span>` +
      (i < t.pattern.length - 1 ? `<span class="arrow">→</span>` : "");
  }).join("");
  return `<div class="card" style="cursor:default">
    <div class="row"><span class="tag">${esc(t.trajectory_id)}</span>
      <span class="pill B">support ${esc(t.support)}</span></div>
    <div class="chain">${chain}</div>
  </div>`;
}

/* ---------------- copilot ---------------- */
const SUGGESTED = [
  "Why is high vibration recurring on P-204?",
  "What assets are most likely to fail?",
  "Show me all compliance gaps",
  "Which pumps are overdue and at risk?",
  "What does the SOP say after a seal replacement?",
];

async function initCopilot() {
  const a = await api("/api/assets");
  $("#copilot-asset").innerHTML = `<option value="">Auto-detect asset</option>` +
    a.assets.map(x => `<option value="${esc(x.asset_id)}">${esc(x.asset_id)} — ${esc(x.name)}</option>`).join("");
  $("#suggested").innerHTML = SUGGESTED.map(q => `<span class="chip">${esc(q)}</span>`).join("");
  $$("#suggested .chip").forEach(c => c.addEventListener("click", () => {
    $("#copilot-q").value = c.textContent; askCopilot();
  }));
  $("#copilot-send").addEventListener("click", askCopilot);
  $("#copilot-q").addEventListener("keydown", e => { if (e.key === "Enter") askCopilot(); });
}

async function askCopilot() {
  const question = $("#copilot-q").value.trim();
  if (!question) return;
  const asset_id = $("#copilot-asset").value || null;
  $("#copilot-answer").innerHTML =
    `<div class="answer"><div class="ans-conf-label">⟢ retrieving from knowledge graph + documents…</div>${skeleton(4)}</div>`;
  const a = await api("/api/copilot", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, asset_id }),
  });
  renderAnswer(a);
}

function confRing(c) {
  const r = 22, circ = 2 * Math.PI * r, off = circ * (1 - c);
  const col = c >= 0.75 ? "var(--ok)" : c >= 0.5 ? "var(--warn)" : "var(--bad)";
  return `<svg class="ring" width="60" height="60" viewBox="0 0 60 60">
    <circle cx="30" cy="30" r="${r}" fill="none" stroke="var(--panel2)" stroke-width="6"/>
    <circle cx="30" cy="30" r="${r}" fill="none" stroke="${col}" stroke-width="6"
      stroke-linecap="round" stroke-dasharray="${circ.toFixed(1)}"
      stroke-dashoffset="${circ.toFixed(1)}" transform="rotate(-90 30 30)"
      style="transition:stroke-dashoffset 1.1s ease" data-off="${off.toFixed(1)}"/>
    <text x="30" y="35" text-anchor="middle" font-size="15" font-weight="800"
      fill="var(--text)">${pct(c)}</text></svg>`;
}

function tableHTML(t) {
  if (!t || !t.rows || !t.rows.length) return "";
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr>` +
    t.columns.map(c => `<th>${esc(c)}</th>`).join("") + `</tr></thead><tbody>` +
    t.rows.map(r => `<tr>` + r.map(c => `<td>${esc(c)}</td>`).join("") + `</tr>`).join("") +
    `</tbody></table></div>`;
}

function renderAnswer(a) {
  if (denied(a)) { $("#copilot-answer").innerHTML = lock(a); return; }
  if (a.error) { $("#copilot-answer").innerHTML = `<div class="answer">${esc(a.error)}</div>`; return; }
  const c = a.confidence;
  let html = `<div class="answer">
    <div class="ans-head">
      ${confRing(c)}
      <div><div class="ans-conf-label">Confidence · ${esc((a.intent || "answer").replace(/_/g, " "))}</div>
        <div class="summary">${esc(a.summary)}</div></div>
    </div>`;

  html += tableHTML(a.table);

  html += confidenceHTML(a.confidence_explanation);

  (a.sections || []).forEach(s => {
    html += `<div class="ans-block"><h4>${esc(s.heading)}</h4><p>${esc(s.body)}</p></div>`;
  });

  if (a.recommended_actions && a.recommended_actions.length) {
    html += `<div class="ans-block"><h4>Recommended action checklist</h4><ul class="actions">` +
      a.recommended_actions.map(x => `<li>${esc(x)}</li>`).join("") + `</ul></div>`;
  }

  if (a.citations && a.citations.length) {
    html += `<div class="cites"><h4 style="color:var(--accent);font-size:13px;text-transform:uppercase;letter-spacing:.8px">Citations</h4>` +
      a.citations.map(ci => `<span class="cite"><span class="score">${ci.score != null ? ci.score : ""}</span>
        <b>${esc(ci.ref)}</b><br>${esc(ci.snippet)}</span>`).join("") + `</div>`;
  }
  html += `</div>`;
  $("#copilot-answer").innerHTML = html;
  // trigger the ring fill animation on next frame
  const ring = $("#copilot-answer .ring circle[data-off]");
  if (ring) requestAnimationFrame(() => { ring.style.strokeDashoffset = ring.dataset.off; });
}

function animateKpis(scope) {
  $$(scope + " .kpi .v").forEach(el => {
    const m = el.textContent.match(/^([\d,]+)(.*)$/);
    if (!m) return;
    const target = parseInt(m[1].replace(/,/g, ""), 10);
    const suffix = m[2];
    if (isNaN(target) || target === 0) return;
    const steps = 22; let i = 0;
    el.textContent = "0" + suffix;
    const tick = setInterval(() => {
      i++; const v = i >= steps ? target : Math.round((target / steps) * i);
      el.textContent = v.toLocaleString() + suffix;
      if (i >= steps) clearInterval(tick);
    }, 20);
  });
}

/* ---------------- risk tab + asset detail ---------------- */
async function loadRiskTab() {
  const a = await api("/api/assets");
  $("#risk-assets").innerHTML = a.assets.map(x => `
    <div class="card" data-asset="${esc(x.asset_id)}">
      <div class="row"><span class="tag">${esc(x.asset_id)} · ${esc(x.name)}</span>
        <span class="pill ${esc(x.criticality)}">${esc(x.criticality)}</span></div>
      <div class="lead">${esc(x.type.replace(/_/g, " "))} · ${esc(x.area)}
        ${x.at_risk ? `· <b>AT RISK ${pct(x.risk_confidence)}%</b>` : "· nominal"}</div>
    </div>`).join("");
  $$("#risk-assets .card").forEach(c => c.addEventListener("click", () => openAsset(c.dataset.asset)));
  $("#asset-detail").innerHTML = "";

  const tj = await api("/api/trajectories");
  $("#trajectories").innerHTML = tj.trajectories.map(trajCard).join("");
}

async function openAsset(id) {
  $("#asset-detail").innerHTML = `<div class="spin">Loading ${esc(id)}…</div>`;
  const d = await api("/api/asset/" + id);
  const ts = await api("/api/timeseries/" + id + "?param=vibration");
  const risk = d.risk || {};
  let html = `<div class="detail-panel">
    <div class="row"><h3 style="margin:0">${esc(d.asset.asset_id)} — ${esc(d.asset.name)}</h3>
      <span class="pill ${esc(d.asset.criticality)}">${esc(d.asset.criticality)}</span></div>
    <p class="muted">${esc(d.asset.type.replace(/_/g, " "))} · ${esc(d.asset.area)} · installed ${esc(d.asset.install_date)}</p>`;

  if (risk.at_risk) {
    const matched = new Set(risk.matched_stages || []);
    const chain = (risk.pattern || []).map((p, i) => {
      const term = i === risk.pattern.length - 1;
      const cls = term ? "term" : (matched.has(p) ? "hit" : "");
      return `<span class="stage ${cls}">${esc(p.replace(/_/g, " "))}</span>` +
        (i < risk.pattern.length - 1 ? `<span class="arrow">→</span>` : "");
    }).join("");
    html += `<div class="conf-row"><span class="conf-badge conf-lo">RISK ${pct(risk.confidence)}%</span>
      <span class="muted">${esc(risk.message)}</span></div>
      <div class="chain">${chain}</div>
      ${confidenceHTML(risk.confidence_explanation)}`;
  } else {
    html += `<p class="muted">${esc(risk.message || "No active failure trajectory.")}</p>`;
  }

  if (d.connected_assets && d.connected_assets.length) {
    html += `<h4 style="margin-top:16px;color:var(--accent)">Connected equipment (from P&ID)</h4>
      <div class="chain">` + d.connected_assets.map(c =>
        `<span class="stage" onclick="openAsset('${esc(c.tag)}')" style="cursor:pointer">
          ${c.direction === "upstream" ? "↑" : "↓"} ${esc(c.tag)} · ${esc(c.name)}</span>`).join("") + `</div>`;
  }

  if (ts.points && ts.points.length) html += sparkline(ts.points);

  if (risk.at_risk) html += `<button class="btn-sm" onclick="simulate('${esc(id)}')">▶ Simulate: act today vs defer 7 days</button>
    <div id="sim-out"></div>`;
  html += `<button class="btn-sm" onclick="loadRCA('${esc(id)}')">🔍 Run RCA + lessons learned</button>
    <div id="rca-out"></div>`;

  html += `<h4 style="margin-top:18px;color:var(--accent)">Event timeline</h4><div class="timeline">` +
    d.timeline.map(e => `<div class="tl-item ${e.etype === "TRIP" ? "term" : ""}">
      <div class="t">${esc(e.ts.slice(0, 16).replace("T", " "))} · ${esc(e.source)}</div>
      <div class="s">${esc(e.subtype.replace(/_/g, " "))}</div>
      <div class="x">${esc(e.text || "")}</div></div>`).join("") + `</div>`;

  html += `<h4 style="color:var(--accent)">Governing documents</h4>` +
    (d.governing_documents.map(x => `<div class="cite"><b>${esc(x.title)}</b> · ${esc(x.doc_id)} v${esc(x.version)}</div>`).join("") || `<p class="muted">none</p>`);

  html += `</div>`;
  $("#asset-detail").innerHTML = html;
  $("#asset-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function sparkline(points) {
  const vals = points.map(p => p.value);
  const W = 600, H = 140, padX = 10, padTop = 12, padBot = 22;
  // fixed scale so the danger/alert thresholds are meaningful
  const lo = 0, hi = Math.max(9.5, Math.max(...vals) + 0.5);
  const X = i => padX + (i / (points.length - 1 || 1)) * (W - 2 * padX);
  const Y = v => H - padBot - ((v - lo) / (hi - lo)) * (H - padTop - padBot);
  const line = points.map((p, i) => `${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ");
  const area = `${X(0)},${Y(lo)} ${line} ${X(points.length - 1)},${Y(lo)}`;
  const last = points[points.length - 1];
  const yThr = (v, label, col) => `
    <line x1="${padX}" y1="${Y(v)}" x2="${W - padX}" y2="${Y(v)}" stroke="${col}"
      stroke-width="1" stroke-dasharray="4 4" opacity="0.7"/>
    <text x="${W - padX}" y="${Y(v) - 4}" text-anchor="end" fill="${col}"
      font-size="11">${label} ${v}</text>`;
  return `<h4 style="margin-top:16px;color:var(--accent)">Vibration trend (mm/s)</h4>
    <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <defs><linearGradient id="vibfill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/></linearGradient></defs>
      ${yThr(7.1, "danger", "#f87171")}
      ${yThr(4.5, "alert", "#fbbf24")}
      <polygon points="${area}" fill="url(#vibfill)"/>
      <polyline fill="none" stroke="#38bdf8" stroke-width="2.5" points="${line}"/>
      <circle cx="${X(points.length - 1).toFixed(1)}" cy="${Y(last.value).toFixed(1)}" r="4"
        fill="#38bdf8"/>
      <text x="${X(points.length - 1).toFixed(1)}" y="${(Y(last.value) - 8).toFixed(1)}"
        text-anchor="end" fill="#e7edf7" font-size="12" font-weight="700">${last.value} now</text>
    </svg>`;
}

async function simulate(id) {
  $("#sim-out").innerHTML = `<div class="spin">Simulating…</div>`;
  const s = await api("/api/simulate/" + id + "?defer=7");
  if (denied(s)) { $("#sim-out").innerHTML = lock(s); return; }
  if (!s.supported) { $("#sim-out").innerHTML = `<p class="muted">${esc(s.message)}</p>`; return; }
  const bi = s.business_impact || {};
  const trip = bi.pump_trip_cost_per_hour || {};
  const cost = bi.estimated_avoided_downtime_cost || {};
  const search = bi.inspection_search_time || {};
  $("#sim-out").innerHTML = `<div class="answer">
    <div class="row"><span>Act <b>today</b></span><span class="status compliant">${pct(s.act_today_trip_risk)}% trip risk</span></div>
    <div class="row" style="margin-top:8px"><span>Defer <b>${s.defer_days} days</b></span><span class="status non_compliant">${pct(s.deferred_trip_risk)}% trip risk</span></div>
    <div class="bar" style="margin-top:12px"><span style="width:${pct(s.risk_reduction)}%"></span></div>
    <p class="lead">Acting now reduces trip risk by <b>${pct(s.risk_reduction)} points</b>. ${esc(s.recommendation)}</p>
    <div class="impact-grid">
      <div><b>Trip cost/hr</b><span>₹${Number(trip.inr || 0).toLocaleString()} / $${Number(trip.usd || 0).toLocaleString()}</span></div>
      <div><b>Downtime avoided</b><span>${esc(bi.average_downtime_avoided_hours || "")} hours</span></div>
      <div><b>Avoided cost</b><span>₹${Number(cost.inr || 0).toLocaleString()} / $${Number(cost.usd || 0).toLocaleString()}</span></div>
      <div><b>Inspection search</b><span>${esc(search.before_hours || "")}h to ${esc(search.after_seconds || "")}s</span></div>
    </div>
  </div>`;
}

async function loadRCA(id) {
  $("#rca-out").innerHTML = `<div class="spin">Building causal graph…</div>`;
  const r = await api("/api/rca/" + id);
  if (denied(r)) { $("#rca-out").innerHTML = lock(r); return; }
  if (!r.available) { $("#rca-out").innerHTML = `<p class="muted">${esc(r.message)}</p>`; return; }
  let html = `<div class="answer"><div class="conf-row">
    <span class="conf-badge ${confClass(r.confidence)}">RCA confidence ${pct(r.confidence)}%</span>
    <span class="muted">${esc(r.mode)} · ${esc(r.incident_ts.slice(0, 10))}</span></div>`;
  html += `<div class="ans-block"><h4>Probable root cause</h4>` +
    r.probable_causes.map(p => `<p>• ${esc(p.cause)} — ${pct(p.confidence)}% (${p.occurrences} cases)</p>`).join("") + `</div>`;
  html += `<div class="ans-block"><h4>Causal chain</h4>` +
    r.causal_chain.map(s => `<p>${esc(s.ts.slice(0, 10))} · <b>${esc(s.stage.replace(/_/g, " "))}</b></p>`).join("") + `</div>`;
  html += `<div class="ans-block"><h4>Preventive playbook</h4>
    <p><b>${esc(r.lessons_learned.title)}</b></p>
    <p>Trigger: ${esc(r.lessons_learned.trigger_pattern)}</p>
    <p>Control: ${esc(r.lessons_learned.preventive_control)}</p>
    <p>Owner: ${esc(r.lessons_learned.owner_role)}</p></div></div>`;
  $("#rca-out").innerHTML = html;
}

/* ---------------- compliance ---------------- */
let COMP_INIT = false;
async function loadCompliance() {
  if (!COMP_INIT) {
    const r = await api("/api/compliance");
    const stds = [...new Set(r.results.map(x => x.standard))];
    $("#comp-standard").innerHTML = `<option value="">All standards</option>` +
      stds.map(s => `<option>${esc(s)}</option>`).join("");
    $("#comp-standard").addEventListener("change", renderCompliance);
    COMP_INIT = true;
  }
  await renderCompliance();
}

async function renderCompliance() {
  const std = $("#comp-standard").value;
  const r = await api("/api/compliance" + (std ? "?standard=" + encodeURIComponent(std) : ""));
  const s = r.summary;
  $("#comp-summary").innerHTML = [
    kpi(s.compliant, "Compliant", "good"),
    kpi(s.due_soon, "Due soon"),
    kpi(s.non_compliant + s.missing, "Gaps", "alert"),
    kpi(pct(s.compliance_rate) + "%", "Rate", s.compliance_rate >= 0.8 ? "good" : "alert"),
  ].join("");

  $("#comp-gaps").innerHTML = `<h2 class="section-title">Clause-by-clause evidence map</h2>` +
    r.results.map(x => `<div class="gap" data-clause="${esc(x.clause_id)}" data-asset="${esc(x.asset_id)}">
      <div><b>${esc(x.asset_id)}</b> · ${esc(x.clause_id)} <span class="muted">(${esc(x.standard)})</span>
        <div class="muted" style="font-size:12px;margin-top:3px">${esc(x.detail || x.title)}</div></div>
      <span class="status ${esc(x.status)}">${esc(x.status.replace("_", " "))}</span>
    </div>`).join("");
  $$("#comp-gaps .gap").forEach(g => g.addEventListener("click",
    () => evidencePack(g.dataset.clause, g.dataset.asset)));
  $("#evidence-pack").innerHTML = "";
}

async function evidencePack(clause, asset) {
  $("#evidence-pack").innerHTML = `<div class="spin">Assembling evidence pack…</div>`;
  const p = await api(`/api/compliance/pack?clause_id=${encodeURIComponent(clause)}&asset_id=${encodeURIComponent(asset)}`);
  let html = `<div class="detail-panel">
    <h3 style="margin:0 0 4px">Evidence pack — ${esc(p.clause.clause_id)}</h3>
    <p class="muted">${esc(p.clause.standard)} · ${esc(p.clause.title)} · asset ${esc(p.asset.asset_id)}</p>
    <p>${esc(p.clause.text)}</p>
    <div class="conf-row"><span class="status ${esc(p.status.status)}">${esc(p.status.status.replace("_", " "))}</span>
      <span class="muted">${esc(p.status.detail || "")}</span></div>
    <h4 style="color:var(--accent)">Supporting records (${p.evidence_records.length})</h4>`;
  html += p.evidence_records.length
    ? p.evidence_records.map(e => `<div class="cite"><b>${esc(e.ts.slice(0, 10))} · ${esc(e.subtype.replace(/_/g, " "))} (${esc(e.status)})</b><br>${esc(e.note || "")}<br><span class="muted">${esc(e.source_ref)}</span></div>`).join("")
    : `<p class="muted">No records found — this is a compliance gap requiring action.</p>`;
  html += `</div>`;
  $("#evidence-pack").innerHTML = html;
  $("#evidence-pack").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------------- P&ID ---------------- */
async function loadPID() {
  $("#pid-canvas").innerHTML = `<div class="spin">Parsing drawing…</div>`;
  const d = await api("/api/pid");
  if (denied(d)) { $("#pid-canvas").innerHTML = lock(d); $("#pid-meta").innerHTML = ""; return; }
  const full = await api("/api/pid/" + d.pids[0].doc_id);
  const p = d.pids[0];
  $("#pid-canvas").innerHTML = `<div class="detail-panel" style="border-color:var(--line)">
    <div style="background:#f7f9fc;border-radius:10px;padding:6px">${full.svg}</div></div>`;
  $("#pid-meta").innerHTML = `
    <h2 class="section-title">Extracted tags (${p.nodes.length})</h2>
    <div class="chain">${p.nodes.map(n => `<span class="stage hit">${esc(n.tag)} · ${esc(n.type)}</span>`).join("")}</div>
    <h2 class="section-title">Inferred connectivity (${p.connections.length})</h2>
    <div class="chain">${p.connections.map(c => `<span class="stage">${esc(c.from)} <span class="arrow">→</span> ${esc(c.to)}</span>`).join("")}</div>
    <p class="muted" style="margin-top:12px">Tags <b>FCV-204</b> and <b>TK-2</b> were discovered on the drawing
      but absent from CMMS/SCADA — auto-registered as new graph nodes.</p>`;
  loadImportDemo();
}

async function loadImportDemo(csvText) {
  const sample = `equipment_tag,event_time,record_type,reading,unit,notes
P-204,2026-06-28T05:45:00,inspection,7.4,mm/s,"Vibrtion route: 1x dominant, interlock bypass still active"
,2026-06-28T06:10:00,work_order,,,"Incomplete CMMS export: alignmnt correction pending, missing tag"
C-12,2026-06-27T23:30:00,alarm,7.2,mm/s,"Healthy compressor vibration spike during startup; cleared in 4 min"`;
  const d = await api("/api/import/preview", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv_text: csvText || sample }),
  });
  if (denied(d)) { $("#import-demo").innerHTML = lock(d); return; }
  $("#import-demo").innerHTML = `<div class="detail-panel">
    <div class="import-head">
      <textarea id="import-csv" spellcheck="false">${esc(csvText || sample)}</textarea>
      <button class="btn-primary" id="import-preview-btn">Preview mapping</button>
    </div>
    <div class="kpi-grid" style="margin-top:12px">
      ${kpi(d.rows_received, "Rows received")}
      ${kpi((d.issues || []).length, "Review flags", (d.issues || []).length ? "alert" : "good")}
      ${kpi((d.mapped_rows || []).filter(r => r.quality === "ready").length, "Ready rows", "good")}
    </div>
    ${importTable(d)}
    <p class="muted">${esc(d.next_step)}</p>
  </div>`;
  $("#import-preview-btn").addEventListener("click", () => loadImportDemo($("#import-csv").value));
}

function importTable(d) {
  const rows = d.mapped_rows || [];
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr>
    <th>Row</th><th>Asset</th><th>Time</th><th>Type</th><th>Param</th><th>Quality</th>
  </tr></thead><tbody>` + rows.map(r => `<tr>
    <td>${esc(r.row)}</td><td>${esc(r.asset_id)}</td><td>${esc(r.ts)}</td>
    <td>${esc(r.event_type)}</td><td>${esc(r.param)}</td><td>${esc(r.quality)}</td>
  </tr>`).join("") + `</tbody></table></div>` +
  (d.issues && d.issues.length ? `<div class="cites">` + d.issues.map(i =>
    `<span class="cite"><b>Row ${esc(i.row)} · ${esc(i.severity)}</b><br>${esc(i.issue)}</span>`).join("") + `</div>` : "");
}

/* ---------------- benchmark ---------------- */
async function loadBenchmark() {
  const el = $("#benchmark");
  el.innerHTML = `<div class="ans-conf-label" style="margin-bottom:10px">⟢ running evaluation harness…</div>${skeleton(5)}`;
  const b = await api("/api/benchmark");
  if (denied(b)) { el.innerHTML = lock(b); return; }
  const ee = b.entity_extraction, pe = b.pid_extraction, sp = b.sequence_prediction,
        nv = b.noisy_validation, cq = b.citation_quality, ti = b.time_to_information,
        lc = b.linkage_completeness, bi = b.business_impact;
  const metric = (l, v, sub) => `<div class="kpi"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div>
    ${sub ? `<div class="muted" style="font-size:11px;margin-top:4px">${esc(sub)}</div>` : ""}</div>`;
  el.innerHTML = `
    <h2 class="section-title">Technical excellence</h2>
    <p class="muted">${esc(b.framing || "On controlled synthetic validation.")}</p>
    <div class="kpi-grid">
      ${metric("Entity extraction F1", ee.f1, `P ${ee.precision} · R ${ee.recall}`)}
      ${metric("P&ID tag F1", pe.tag_f1, `connectivity F1 ${pe.connectivity_f1}`)}
      ${metric("Trajectory pred. F1", sp.f1, `TP ${sp.tp} · FP ${sp.fp} · FN ${sp.fn}`)}
      ${metric("Citation rate", pct(cq.citation_rate) + "%", "answers source-backed")}
    </div>
    <h2 class="section-title">Noisy validation</h2>
    <p class="muted">${esc(nv.framing)}</p>
    <div class="kpi-grid">
      ${metric("Dirty entity F1", nv.entity_extraction.f1, `P ${nv.entity_extraction.precision} / R ${nv.entity_extraction.recall}`)}
      ${metric("Hard trajectory F1", nv.sequence_prediction.f1, `TP ${nv.sequence_prediction.tp} / FP ${nv.sequence_prediction.fp} / FN ${nv.sequence_prediction.fn}`)}
      ${metric("Counterexamples", nv.counterexamples.length, nv.counterexamples.join(", "))}
    </div>
    <h2 class="section-title">CHRONOS vs traditional search</h2>
    <div class="answer">
      <div class="row"><span><b>CHRONOS copilot</b></span>
        <span class="status compliant">${ti.copilot_latency_ms} ms</span></div>
      <p class="lead">${esc(ti.copilot_returns)} · ${ti.copilot_citations} citations</p>
      <div class="row" style="margin-top:10px"><span><b>Keyword search</b></span>
        <span class="status non_compliant">${ti.baseline_latency_ms} ms</span></div>
      <p class="lead">${esc(ti.baseline_returns)} · ${ti.baseline_citations} citations</p>
      <p class="muted" style="margin-top:10px">${esc(ti.interpretation)}</p>
    </div>
    <h2 class="section-title">Scalability &amp; linkage</h2>
    <div class="kpi-grid">
      ${metric("Event→asset linkage", pct(lc.linkage_rate) + "%")}
      ${metric("Cross-system links", lc.cross_system_auto_links)}
      ${metric("P&ID connectivity", lc.pid_connectivity_edges)}
      ${metric("Sources unified", lc.source_systems_unified)}
    </div>
    <h2 class="section-title">Business impact estimate</h2>
    <div class="kpi-grid">
      ${metric("Pump trip cost/hr", `₹${Number(bi.pump_trip_cost_per_hour.inr).toLocaleString()}`, `$${Number(bi.pump_trip_cost_per_hour.usd).toLocaleString()} per hour`)}
      ${metric("Downtime avoided", `${bi.average_downtime_avoided_hours}h`, "average avoided trip duration")}
      ${metric("Avoided downtime cost", `₹${Number(bi.estimated_avoided_downtime_cost.inr).toLocaleString()}`, `$${Number(bi.estimated_avoided_downtime_cost.usd).toLocaleString()}`)}
      ${metric("Inspection search", `${bi.inspection_search_time.before_hours}h → ${bi.inspection_search_time.after_seconds}s`, "hours reduced to seconds")}
    </div>
    <p class="muted">${esc(bi.basis)}</p>`;
}

function confidenceHTML(items) {
  if (!items || !items.length) return "";
  return `<div class="ans-block"><h4>Confidence explanation</h4>
    <div class="explain-grid">` + items.map(x => `<div class="explain-item">
      <b>${esc(x.factor)}</b><span>${esc(x.value)}</span><em>${esc(x.weight)}</em>
    </div>`).join("") + `</div></div>`;
}

/* ---------------- onboarding + guided tour ---------------- */
function hideWelcome() { const w = $("#welcome"); if (w) w.hidden = true; try { localStorage.setItem("chronos_seen", "1"); } catch (e) {} }
$("#skip-welcome") && $("#skip-welcome").addEventListener("click", hideWelcome);
$("#start-tour") && $("#start-tour").addEventListener("click", () => { hideWelcome(); startTour(); });
$("#help-btn") && $("#help-btn").addEventListener("click", () => { hideWelcome(); startTour(); });

const TOUR = [
  { sel: "#status-banner", step: "1 / 5", title: "Plant status", body: "A plain-language headline telling you whether anything needs your attention right now." },
  { sel: "#attention", step: "2 / 5", title: "Early warning", body: "CHRONOS noticed this machine entering a known failure pattern — and how long you likely have. The button gives you a sourced, step-by-step fix." },
  { sel: '[data-view="copilot"]', step: "3 / 5", title: "Ask anything", body: "Type a question in plain English. You get a clear answer with a confidence score and links to the exact records behind it." },
  { sel: '[data-view="risk"]', step: "4 / 5", title: "Predictions", body: "See every machine scored for failure risk, open its full timeline, and simulate “fix now vs wait a week.”" },
  { sel: '[data-view="compliance"]', step: "5 / 5", title: "Compliance", body: "Instantly find overdue inspections and generate an audit-ready evidence pack — no more digging through folders." },
];
let tourI = 0, tourEls = null;

function startTour() {
  const home = $('[data-view="dashboard"]');
  if (home && !home.classList.contains("active")) home.click();
  tourI = 0;
  if (!tourEls) {
    const hole = document.createElement("div"); hole.className = "tour-hole";
    const bubble = document.createElement("div"); bubble.className = "tour-bubble";
    document.body.appendChild(hole); document.body.appendChild(bubble);
    tourEls = { hole, bubble };
    window.addEventListener("resize", positionTour);
  }
  showTourStep();
}
function endTour() {
  if (tourEls) { tourEls.hole.remove(); tourEls.bubble.remove(); tourEls = null; }
  window.removeEventListener("resize", positionTour);
  try { localStorage.setItem("chronos_seen", "1"); } catch (e) {}
}
function showTourStep() {
  const s = TOUR[tourI];
  const dots = TOUR.map((_, i) => `<span class="dot ${i === tourI ? "on" : ""}"></span>`).join("");
  tourEls.bubble.innerHTML =
    `<div class="tour-step">${esc(s.step)} · guided tour</div><h4>${esc(s.title)}</h4><p>${esc(s.body)}</p>
     <div class="tour-nav"><button class="tour-skip">Skip</button><div class="dots">${dots}</div>
     <button class="tour-next">${tourI === TOUR.length - 1 ? "Got it" : "Next →"}</button></div>`;
  tourEls.bubble.querySelector(".tour-skip").onclick = endTour;
  tourEls.bubble.querySelector(".tour-next").onclick = () => {
    if (tourI >= TOUR.length - 1) endTour(); else { tourI++; showTourStep(); }
  };
  positionTour();
}
function positionTour() {
  if (!tourEls) return;
  const t = document.querySelector(TOUR[tourI].sel);
  if (!t) return;
  t.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => {
    if (!tourEls) return;
    const r = t.getBoundingClientRect(), pad = 8, b = tourEls.bubble, hole = tourEls.hole;
    hole.style.left = (r.left - pad) + "px"; hole.style.top = (r.top - pad) + "px";
    hole.style.width = (r.width + pad * 2) + "px"; hole.style.height = (r.height + pad * 2) + "px";
    const bw = Math.min(320, window.innerWidth * 0.9);
    const left = Math.max(12, Math.min(r.left, window.innerWidth - bw - 12));
    b.style.left = left + "px";
    const bh = b.offsetHeight || 180;
    let top = r.bottom + 14;
    if (top + bh > window.innerHeight - 12) top = Math.max(12, r.top - bh - 14);
    b.style.top = top + "px";
  }, 200);
}

/* ---------------- boot ---------------- */
updateContext("dashboard");
initAuthDemo().then(() => { loadDashboard(); initCopilot(); });
try { if (!localStorage.getItem("chronos_seen")) setTimeout(() => { const w = $("#welcome"); if (w) w.hidden = false; }, 450); } catch (e) {}
