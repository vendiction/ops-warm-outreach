"""Human send console — the compliant DM path.

Lists approved IG/FB/LinkedIn drafts so a human can copy the text, send it from the real
app while genuinely logged in, and mark it sent. Enforces a per-channel daily cap as a
guardrail. Also lets the operator paste a reply, which the triage classifier tags and
(if interested) pings Discord. No browser automation, no proxies, no evasion — just a queue.

Daily cap configuration (no code change needed):
    DM_DAILY_CAP=20            global default for every channel
    DM_DAILY_CAP_IG=30         optional per-channel override (dm_ig)
    DM_DAILY_CAP_LINKEDIN=15   optional per-channel override (dm_linkedin)
    DM_DAILY_CAP_FB=10         optional per-channel override (dm_fb)
Set the env var (in .env or on the host) and recreate the container:
    docker compose up -d --force-recreate send_console
"""
import os
import sys
import json
from contextlib import contextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from psycopg_pool import ConnectionPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from reply_triage.classifier import classify_reply  # noqa: E402

# --- Cap config: global default + optional per-channel overrides, all via env ---
_DEFAULT_CAP = int(os.getenv("DM_DAILY_CAP", "20"))
DM_CAPS = {
    "dm_ig": int(os.getenv("DM_DAILY_CAP_IG", _DEFAULT_CAP)),
    "dm_linkedin": int(os.getenv("DM_DAILY_CAP_LINKEDIN", _DEFAULT_CAP)),
    "dm_fb": int(os.getenv("DM_DAILY_CAP_FB", _DEFAULT_CAP)),
}
def cap_for(channel: str) -> int:
    return DM_CAPS.get(channel, _DEFAULT_CAP)

DISCORD_WEBHOOK = os.getenv("DISCORD_HOTLEAD_WEBHOOK", os.getenv("DISCORD_DIGEST_WEBHOOK", ""))
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True)
    return _pool


@contextmanager
def _conn():
    with _get_pool().connection() as c:
        yield c


app = FastAPI(title="send-console", version="0.2.0")

_CHANNEL_HANDLE = {
    "dm_ig": "founder_ig_handle",
    "dm_linkedin": "founder_linkedin_url",
    "dm_fb": "founder_fb_handle",
}


def _sent_today():
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT channel::text, COUNT(*) FROM lead_outreach "
            "WHERE status='sent' AND sent_at::date = CURRENT_DATE "
            "AND channel IN ('dm_ig','dm_linkedin','dm_fb') GROUP BY 1")
        return dict(cur.fetchall())


def list_queue():
    with _conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT lo.id, lo.lead_id, lo.channel::text, lo.sequence_step,
                   COALESCE(lo.approved_body, lo.draft_body) AS body,
                   l.company_name, l.qualification_score,
                   l.founder_ig_handle, l.founder_linkedin_url, l.founder_fb_handle
            FROM lead_outreach lo JOIN leads l ON l.id = lo.lead_id
            WHERE lo.status = 'approved' AND lo.channel IN ('dm_ig','dm_linkedin','dm_fb')
            ORDER BY l.qualification_score DESC NULLS LAST, lo.approved_at ASC NULLS LAST
        """)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    sent = _sent_today()
    for r in rows:
        handle_col = _CHANNEL_HANDLE.get(r["channel"])
        r["handle"] = r.get(handle_col) if handle_col else None
    caps = {ch: {"sent": sent.get(ch, 0), "cap": cap_for(ch),
                 "remaining": max(0, cap_for(ch) - sent.get(ch, 0))}
            for ch in ("dm_ig", "dm_linkedin", "dm_fb")}
    return {"queue": rows, "caps": caps}


def list_history(limit: int = 100):
    """Recent sent + skipped DMs, newest first — the logs page."""
    with _conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT lo.id, lo.channel::text, lo.status::text, lo.sequence_step,
                   COALESCE(lo.approved_body, lo.draft_body) AS body,
                   l.company_name, l.qualification_score,
                   COALESCE(lo.sent_at, lo.updated_at) AS actioned_at
            FROM lead_outreach lo JOIN leads l ON l.id = lo.lead_id
            WHERE lo.status IN ('sent','skipped') AND lo.channel IN ('dm_ig','dm_linkedin','dm_fb')
            ORDER BY COALESCE(lo.sent_at, lo.updated_at) DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        if r.get("actioned_at"):
            r["actioned_at"] = r["actioned_at"].isoformat()
    return {"history": rows}


def mark_sent(outreach_id: int):
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT channel::text, lead_id FROM lead_outreach WHERE id=%s AND status='approved'", (outreach_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "not an approved draft")
        channel, lead_id = row
        cap = cap_for(channel)
        cur.execute("SELECT COUNT(*) FROM lead_outreach WHERE channel=%s AND status='sent' AND sent_at::date=CURRENT_DATE", (channel,))
        if cur.fetchone()[0] >= cap:
            raise HTTPException(429, f"daily cap ({cap}) reached for {channel}")
        cur.execute("UPDATE lead_outreach SET status='sent', sent_at=NOW(), updated_at=NOW() WHERE id=%s", (outreach_id,))
        cur.execute("INSERT INTO outreach_events (lead_id, outreach_id, event_type, event_data, actor) "
                    "VALUES (%s,%s,'send',%s::jsonb,'human')", (lead_id, outreach_id, json.dumps({"channel": channel, "via": "send_console"})))
        c.commit()
    return {"ok": True}


def skip(outreach_id: int):
    with _conn() as c, c.cursor() as cur:
        cur.execute("UPDATE lead_outreach SET status='skipped', updated_at=NOW() WHERE id=%s AND status='approved' RETURNING lead_id", (outreach_id,))
        row = cur.fetchone()
        if row:
            cur.execute("INSERT INTO outreach_events (lead_id, outreach_id, event_type, actor) VALUES (%s,%s,'skipped','human')", (row[0], outreach_id))
        c.commit()
    return {"ok": True}


def log_reply(outreach_id: int, text: str):
    result = classify_reply(text)
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT lead_id FROM lead_outreach WHERE id=%s", (outreach_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "outreach not found")
        lead_id = row[0]
        cur.execute("""UPDATE lead_outreach SET reply_body=%s, reply_received_at=NOW(),
                       reply_classification=%s::reply_classification_enum, reply_reasoning=%s, updated_at=NOW()
                       WHERE id=%s""", (text, result["classification"], result["reasoning"], outreach_id))
        cur.execute("INSERT INTO outreach_events (lead_id, outreach_id, event_type, event_data, actor) "
                    "VALUES (%s,%s,'reply',%s::jsonb,'human')", (lead_id, outreach_id, json.dumps(result)))
        cur.execute("SELECT company_name FROM leads WHERE id=%s", (lead_id,))
        company = (cur.fetchone() or [None])[0]
        c.commit()
    if result["classification"] == "interested" and DISCORD_WEBHOOK:
        try:
            httpx.post(DISCORD_WEBHOOK, json={"content": f"🔥 **Interested reply** — {company} (lead #{lead_id})\n> {text[:300]}\n_{result['reasoning']}_ · urgency: {result['urgency']}"}, timeout=10)
        except Exception:
            pass
    return result


class ReplyIn(BaseModel):
    outreach_id: int
    text: str


@app.get("/api/queue")
def api_queue():
    return list_queue()


@app.get("/api/history")
def api_history(limit: int = 100):
    return list_history(limit)


@app.post("/api/sent/{outreach_id}")
def api_sent(outreach_id: int):
    return mark_sent(outreach_id)


@app.post("/api/skip/{outreach_id}")
def api_skip(outreach_id: int):
    return skip(outreach_id)


@app.post("/api/reply")
def api_reply(r: ReplyIn):
    return log_reply(r.outreach_id, r.text)


@app.get("/health")
def health():
    return {"status": "ok", "caps": DM_CAPS}


@app.get("/", response_class=HTMLResponse)
def index():
    return _PAGE


@app.get("/history", response_class=HTMLResponse)
def history_page():
    return _PAGE


_PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Send Console</title>
<style>
:root{
  --bg:#f4f5f7; --panel:#ffffff; --panel-2:#fafbfc; --ink:#1a1d21; --muted:#6b7280;
  --line:#e5e7eb; --accent:#4f46e5; --accent-ink:#fff; --ok:#059669; --warn:#d97706;
  --skip:#6b7280; --chip:#eef2ff; --chip-ink:#4338ca; --shadow:0 1px 3px rgba(0,0,0,.08);
}
[data-theme=dark]{
  --bg:#0e1116; --panel:#171b22; --panel-2:#1c2129; --ink:#e6e9ef; --muted:#9aa4b2;
  --line:#262c36; --accent:#6366f1; --accent-ink:#fff; --ok:#10b981; --warn:#f59e0b;
  --skip:#8b95a3; --chip:#1e2333; --chip-ink:#a5b4fc; --shadow:0 1px 3px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--ink);transition:background .2s,color .2s}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);
  padding:14px 22px;display:flex;align-items:center;gap:16px;box-shadow:var(--shadow)}
header h1{font-size:17px;margin:0;font-weight:650;letter-spacing:-.01em}
header .sub{color:var(--muted);font-size:13px}
nav{display:flex;gap:6px;margin-left:8px}
nav a{padding:6px 13px;border-radius:8px;text-decoration:none;color:var(--muted);font-weight:550;font-size:14px}
nav a.on{background:var(--chip);color:var(--chip-ink)}
.spacer{flex:1}
.toggle{cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);
  border-radius:9px;padding:7px 12px;font-size:14px;display:flex;align-items:center;gap:7px}
.wrap{max-width:920px;margin:22px auto;padding:0 18px}
.caps{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.cap{flex:1;min-width:150px;background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:13px 16px;box-shadow:var(--shadow)}
.cap .label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.cap .val{font-size:22px;font-weight:700;margin-top:3px}
.cap .bar{height:5px;background:var(--line);border-radius:3px;margin-top:9px;overflow:hidden}
.cap .bar>i{display:block;height:100%;background:var(--accent);border-radius:3px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;
  margin-bottom:14px;box-shadow:var(--shadow)}
.card .top{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.card .co{font-weight:650;font-size:16px}
.chip{background:var(--chip);color:var(--chip-ink);border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600}
.chip.score{background:transparent;border:1px solid var(--line);color:var(--muted)}
.handle{color:var(--accent);font-weight:600;font-size:14px;text-decoration:none;cursor:pointer}
.handle:hover{text-decoration:underline}
.body{white-space:pre-wrap;background:var(--panel-2);border:1px solid var(--line);border-radius:10px;
  padding:13px;font-size:14px;margin:8px 0 12px;max-height:280px;overflow:auto}
.row{display:flex;gap:9px;flex-wrap:wrap}
button.act{border:none;border-radius:9px;padding:9px 15px;font-weight:600;font-size:14px;cursor:pointer}
.send{background:var(--accent);color:var(--accent-ink)}
.copy{background:var(--panel-2);color:var(--ink);border:1px solid var(--line)}
.skipb{background:transparent;color:var(--skip);border:1px solid var(--line)}
.empty{text-align:center;color:var(--muted);padding:60px 0}
.empty .big{font-size:40px;margin-bottom:8px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);font-size:14px}
th{background:var(--panel-2);color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:none}
.badge{font-size:12px;font-weight:650;padding:2px 9px;border-radius:999px}
.badge.sent{background:rgba(5,150,105,.13);color:var(--ok)}
.badge.skipped{background:rgba(107,114,128,.15);color:var(--skip)}
.tcell{max-width:340px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--bg);
  padding:11px 18px;border-radius:10px;font-size:14px;opacity:0;transition:opacity .2s;pointer-events:none}
.toast.show{opacity:1}
</style></head><body>
<header>
  <h1>&#128238; Send Console</h1>
  <nav>
    <a href="/" id="nav-queue">Queue</a>
    <a href="/history" id="nav-history">History</a>
  </nav>
  <span class="sub" id="sub"></span>
  <span class=spacer></span>
  <button class=toggle id=themeBtn onclick=toggleTheme()><span id=themeIcon>&#127769;</span><span id=themeLbl>Dark</span></button>
</header>
<div class=wrap id=app></div>
<div class=toast id=toast></div>
<script>
const CH={dm_ig:"Instagram",dm_linkedin:"LinkedIn",dm_fb:"Facebook"};
const isHistory=location.pathname.replace(/\/$/,"")==="/history";
function getTheme(){const m=document.cookie.match(/theme=(\w+)/);return m?m[1]:"light";}
function setTheme(t){document.documentElement.setAttribute("data-theme",t);
  document.cookie="theme="+t+";path=/;max-age=31536000";
  themeIcon.textContent=t==="dark"?"\u2600\ufe0f":"\ud83c\udf19";themeLbl.textContent=t==="dark"?"Light":"Dark";}
function toggleTheme(){setTheme(getTheme()==="dark"?"light":"dark");}
setTheme(getTheme());
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");
  setTimeout(()=>t.classList.remove("show"),1800);}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function profileUrl(channel,handle){
  if(!handle) return "#";
  const h=String(handle).trim();
  if(/^https?:\/\//i.test(h)) return h;                 // already a full URL (LinkedIn)
  const u=h.replace(/^@/,"");                            // strip leading @
  if(channel==="dm_ig") return "https://instagram.com/"+u;
  if(channel==="dm_fb") return "https://facebook.com/"+u;
  if(channel==="dm_linkedin") return "https://www.linkedin.com/in/"+u;
  return h;
}
function chandle(channel,handle){return profileUrl(channel,handle);}
document.getElementById(isHistory?"nav-history":"nav-queue").classList.add("on");
async function loadQueue(){
  const d=await (await fetch("/api/queue")).json();
  const caps=d.caps||{};
  let ch=`<div class=caps>`+Object.keys(CH).map(k=>{
    const c=caps[k]||{sent:0,cap:0,remaining:0};const pct=c.cap?Math.min(100,100*c.sent/c.cap):0;
    return `<div class=cap><div class=label>${CH[k]}</div>
      <div class=val>${c.sent}<span style="color:var(--muted);font-size:14px"> / ${c.cap}</span></div>
      <div class=bar><i style="width:${pct}%"></i></div></div>`;}).join("")+`</div>`;
  document.getElementById("sub").textContent=(d.queue.length||0)+" waiting";
  if(!d.queue.length){document.getElementById("app").innerHTML=ch+
    `<div class=empty><div class=big>&#9989;</div>Queue is clear &mdash; nothing waiting to send.</div>`;return;}
  document.getElementById("app").innerHTML=ch+d.queue.map(q=>`
    <div class=card id=card-${q.id}>
      <div class=top>
        <span class=co>${esc(q.company_name)||"&mdash;"}</span>
        <span class=chip>${CH[q.channel]||q.channel}</span>
        <span class="chip score">score ${q.qualification_score??"&ndash;"}</span>
        <span style=flex:1></span>
        ${q.handle?`<a class=handle href="${profileUrl(q.channel,q.handle)}" target=_blank rel=noopener>${esc(q.handle)} &#8599;</a>`:""}
      </div>
      <div class=body id=body-${q.id}>${esc(q.body)}</div>
      <div class=row>
        <button class="act copy" onclick="copyBody(${q.id})">&#128203; Copy text</button>
        <button class="act send" onclick="markSent(${q.id})">&#9989; Mark sent</button>
        <button class="act skipb" onclick="doSkip(${q.id})">Skip</button>
      </div>
    </div>`).join("");
}
async function loadHistory(){
  const d=await (await fetch("/api/history?limit=150")).json();
  document.getElementById("sub").textContent=(d.history.length||0)+" logged";
  if(!d.history.length){document.getElementById("app").innerHTML=
    `<div class=empty><div class=big>&#128209;</div>No sent or skipped DMs yet.</div>`;return;}
  document.getElementById("app").innerHTML=`<table><thead><tr>
    <th>When</th><th>Company</th><th>Channel</th><th>Status</th><th>Message</th></tr></thead><tbody>`+
    d.history.map(h=>{const t=h.actioned_at?new Date(h.actioned_at).toLocaleString():"&mdash;";
      return `<tr><td style="color:var(--muted);white-space:nowrap">${t}</td>
        <td>${esc(h.company_name)||"&mdash;"}</td><td>${CH[h.channel]||h.channel}</td>
        <td><span class="badge ${h.status}">${h.status}</span></td>
        <td class=tcell>${esc(h.body)}</td></tr>`;}).join("")+`</tbody></table>`;
}
async function copyBody(id){const t=document.getElementById("body-"+id).innerText;
  try{await navigator.clipboard.writeText(t);toast("Copied to clipboard");}catch{toast("Copy failed");}}
async function markSent(id){const r=await fetch("/api/sent/"+id,{method:"POST"});
  if(r.ok){toast("Marked sent");loadQueue();}else{const e=await r.json();toast(e.detail||"Failed");}}
async function doSkip(id){const r=await fetch("/api/skip/"+id,{method:"POST"});
  if(r.ok){toast("Skipped");loadQueue();}}
if(isHistory){loadHistory();}else{loadQueue();setInterval(loadQueue,15000);}
</script></body></html>"""
