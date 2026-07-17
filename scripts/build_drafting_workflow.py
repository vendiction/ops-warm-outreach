#!/usr/bin/env python3
"""Generates shared/n8n-templates/draft_outreach.json, embedding the drafting system
prompts and the forbidden-phrase blocklist VERBATIM from prompts/. Re-run after any
prompt change so the workflow never drifts from the canonical prompts."""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "prompts"


def system_from(md_name: str) -> str:
    text = (P / md_name).read_text(encoding="utf-8")
    return text[text.index("## System"):].strip()


sonnet_sys = system_from("drafting_sonnet.md")
opus_extra = system_from("drafting_opus.md")   # references sonnet; we concat for a self-contained hot prompt
email_sys = system_from("drafting_email.md")

# opus system = sonnet base + opus emphasis (the opus file explicitly says "read sonnet first")
opus_sys = sonnet_sys + "\n\n---\n\n# HOT-QUEUE EMPHASIS (score 20+)\n\n" + opus_extra

# --- forbidden phrases: parse "- phrase" bullets, drop the backtick punctuation entries ---
fp_text = (P / "forbidden_phrases.md").read_text(encoding="utf-8")
phrases = []
for line in fp_text.splitlines():
    m = re.match(r"^- (.+)$", line.strip())
    if m and "`" not in m.group(1):
        phrases.append(m.group(1).strip())
# de-dupe preserve order
seen = set()
phrases = [p for p in phrases if not (p.lower() in seen or seen.add(p.lower()))]


def lit(s: str) -> str:
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


expand_js = (
    "// Expand each scored lead into one job per supported channel.\n"
    f"const DM_SONNET = `{lit(sonnet_sys)}`;\n"
    f"const DM_OPUS = `{lit(opus_sys)}`;\n"
    f"const EMAIL_SYS = `{lit(email_sys)}`;\n"
    "const out = [];\n"
    "for (const it of $input.all()) {\n"
    "  const r = it.json;\n"
    "  const isHot = (r.qualification_score || 0) >= 20;\n"
    "  const model = isHot ? 'opus' : 'sonnet';\n"
    "  const modelId = isHot ? 'claude-opus-4-7' : 'claude-sonnet-4-6';\n"
    "  const maxTokens = isHot ? 1000 : 800;\n"
    "  const dmSystem = isHot ? DM_OPUS : DM_SONNET;\n"
    "  const firstName = (r.founder_name || '').split(' ')[0] || null;\n"
    "  const prospect = { first_name: firstName, company_name: r.company_name, recent_social_posts: r.recent_social_posts || [] };\n"
    "  const channels = [];\n"
    "  if (r.founder_ig_handle) channels.push('dm_ig');\n"
    "  if (r.founder_linkedin_url) channels.push('dm_linkedin');\n"
    "  if (r.founder_fb_handle) channels.push('dm_fb');\n"
    "  if (r.founder_email) channels.push('cold_email');\n"
    "  for (const channel of channels) {\n"
    "    const isDm = channel.startsWith('dm_');\n"
    "    const payload = { channel, prospect, audit_gap: (r.gap_summary || ''), gap_summary: (r.gap_summary || ''), tech_stack: r.tech_stack || {} };\n"
    "    out.push({ json: { lead_id: r.lead_id, channel, is_dm: isDm, model, model_id: modelId, max_tokens: maxTokens, system: (isDm ? dmSystem : EMAIL_SYS), payload } });\n"
    "  }\n"
    "}\n"
    "return out;"
)

validate_js = (
    f"const FORBIDDEN = {json.dumps(phrases)};\n"
    "const respBody = $json;\n"
    "let text = '';\n"
    "try { text = (respBody.content || []).filter(b => b.type === 'text').map(b => b.text).join(''); } catch (e) {}\n"
    "let parsed;\n"
    "try { parsed = JSON.parse((text || '').replace(/```json|```/g, '').trim()); }\n"
    "catch (e) { throw new Error('malformed_json_from_model'); }\n"
    "const job = $('Loop jobs').item.json;\n"
    "const isDm = job.is_dm;\n"
    "const msgs = parsed.messages || [];\n"
    "if (!Array.isArray(msgs) || msgs.length === 0) throw new Error('no_messages');\n"
    "const expected = isDm ? 3 : 4;\n"
    "if (msgs.length !== expected) throw new Error('expected_' + expected + '_messages_got_' + msgs.length);\n"
    "const gap = (job.payload.gap_summary || '').toLowerCase();\n"
    "const gapWords = gap.split(/[^a-z0-9]+/).filter(w => w.length > 4);\n"
    "const rows = [];\n"
    "for (const m of msgs) {\n"
    "  if (!m.body) throw new Error('empty_body_step_' + m.step);\n"
    "  let stored = m.body;\n"
    "  if (!isDm) {\n"
    "    if (!m.subject) throw new Error('email_missing_subject_step_' + m.step);\n"
    "    stored = 'Subject: ' + m.subject + '\\n\\n' + m.body;\n"
    "  }\n"
    "  const lc = (m.body + ' ' + (m.subject || '')).toLowerCase();\n"
    "  for (const p of FORBIDDEN) { if (lc.includes(p.toLowerCase())) throw new Error('forbidden_phrase:' + p + '@' + m.step); }\n"
    "  if (m.body.includes(' \\u2014 ')) throw new Error('em_dash@' + m.step);\n"
    "  if (m.body.includes('!!!')) throw new Error('triple_bang@' + m.step);\n"
    "  if (isDm && m.step === 1 && m.body.length > 160) throw new Error('msg1_over_160:' + m.body.length);\n"
    "  if (m.step === 1 && gapWords.length && !gapWords.some(w => lc.includes(w))) throw new Error('step1_no_gap_reference');\n"
    "  rows.push({ step: m.step, body: stored, char_count: stored.length });\n"
    "}\n"
    "return [{ json: { lead_id: job.lead_id, channel: job.channel, model: job.model, messages: rows } }];"
)

draft_body_expr = ("={{ { model: $json.model_id, max_tokens: $json.max_tokens, temperature: 0.7, "
                   "system: $json.system, messages: [ { role: 'user', content: JSON.stringify($json.payload) } ] } }}")
retry_body_expr = ("={{ { model: $('Loop jobs').item.json.model_id, max_tokens: $('Loop jobs').item.json.max_tokens, "
                   "temperature: 0.7, system: $('Loop jobs').item.json.system + '\\n\\nYour previous draft FAILED validation. "
                   "Rewrite strictly obeying: message 1 <=160 chars, reference the audit gap AND a recent post, no forbidden "
                   "phrases, no em-dashes, no !!!. Return only the JSON.', messages: [ { role: 'user', content: "
                   "JSON.stringify($('Loop jobs').item.json.payload) } ] } }}")

anthropic_headers = {"parameters": [
    {"name": "anthropic-version", "value": "2023-06-01"},
    {"name": "content-type", "value": "application/json"}]}
anthropic_cred = {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "Anthropic API (x-api-key)"}}
pg_cred = {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}}

SAVE_QUERY = ("INSERT INTO lead_outreach (lead_id, channel, sequence_step, status, draft_body, draft_char_count, draft_model)\n"
              "SELECT $1, $2::outreach_channel_enum, m.step, 'draft', m.body, m.char_count, $3\n"
              "FROM jsonb_to_recordset($4::jsonb) AS m(step int, body text, char_count int)\n"
              "WHERE NOT EXISTS (SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = $1 AND lo.channel = $2::outreach_channel_enum);")
SAVE_REPL = "={{ [$json.lead_id, $json.channel, $json.model, JSON.stringify($json.messages)] }}"

nodes = [
    {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}},
     "id": "sched", "name": "Every 5 min", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [-1180, 300]},
    {"parameters": {"operation": "executeQuery",
        "query": "SELECT l.id AS lead_id, l.company_name, l.founder_name,\n       l.founder_ig_handle, l.founder_linkedin_url, l.founder_fb_handle, l.founder_email,\n       l.qualification_score,\n       e.recent_social_posts, e.tech_stack,\n       a.gap_summary\nFROM leads l\nLEFT JOIN lead_enrichment e ON e.lead_id = l.id\nLEFT JOIN lead_audits a ON a.lead_id = l.id AND a.audit_status = 'complete'\nWHERE l.qualification_score >= 15\n  AND l.is_archived = FALSE\n  AND NOT EXISTS (SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = l.id)\nORDER BY l.qualification_score DESC\nLIMIT 10;",
        "options": {}},
     "id": "pg-select", "name": "Scored Leads To Draft", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6, "position": [-960, 300], "credentials": pg_cred},
    {"parameters": {"jsCode": expand_js},
     "id": "expand", "name": "Expand To Channel Jobs", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-740, 300]},
    {"parameters": {"batchSize": 1, "options": {}},
     "id": "loop", "name": "Loop jobs", "type": "n8n-nodes-base.splitInBatches", "typeVersion": 3, "position": [-520, 300]},
    {"parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": anthropic_headers,
        "sendBody": True, "specifyBody": "json", "jsonBody": draft_body_expr, "options": {"timeout": 60000}},
     "id": "draft", "name": "Draft (Claude)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [-300, 200],
     "credentials": anthropic_cred, "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 4000},
    {"parameters": {"jsCode": validate_js},
     "id": "validate", "name": "Validate", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-80, 200], "onError": "continueErrorOutput"},
    {"parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": anthropic_headers,
        "sendBody": True, "specifyBody": "json", "jsonBody": retry_body_expr, "options": {"timeout": 60000}},
     "id": "draft-retry", "name": "Draft Retry (corrective)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [140, 360],
     "credentials": anthropic_cred, "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 4000},
    {"parameters": {"jsCode": validate_js},
     "id": "validate-retry", "name": "Validate Retry", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [360, 360], "onError": "continueErrorOutput"},
    {"parameters": {"operation": "executeQuery", "query": SAVE_QUERY, "options": {"queryReplacement": SAVE_REPL}},
     "id": "save", "name": "Save Drafts", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6, "position": [360, 140], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "INSERT INTO outreach_events (lead_id, event_type, event_data, actor)\nVALUES ($1, 'draft', $2::jsonb, 'system');",
        "options": {"queryReplacement": "={{ [ $('Loop jobs').item.json.lead_id, JSON.stringify({ channel: $('Loop jobs').item.json.channel, model: $('Loop jobs').item.json.model, messages: ($('Loop jobs').item.json.is_dm ? 3 : 4) }) ] }}"}},
     "id": "event", "name": "Log Draft Event", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6, "position": [580, 140], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "INSERT INTO outreach_events (lead_id, event_type, event_data, actor)\nVALUES ($1, 'draft_failed', $2::jsonb, 'system');",
        "options": {"queryReplacement": "={{ [$('Loop jobs').item.json.lead_id, JSON.stringify({ channel: $('Loop jobs').item.json.channel, error: ($json.error && $json.error.message) ? $json.error.message : 'validation_failed_twice' }) ] }}"}},
     "id": "event-fail", "name": "Log Draft Failed", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6, "position": [580, 480], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"amount": 2, "unit": "seconds"},
     "id": "jitter", "name": "Jitter", "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": [820, 300]},
    {"parameters": {"content": "## Draft Outreach\nEvery 5 min: pulls score>=15 leads with no drafts yet, expands to one job per supported channel (IG/LinkedIn/FB DM if a handle exists, cold email if an address exists), drafts with Sonnet (15-19) or Opus (20+).\n\n**Prompts + forbidden-phrase list are embedded VERBATIM** from prompts/ by scripts/build_drafting_workflow.py — do not hand-edit; re-run the builder after prompt changes.\n\n**Validator (hard gates):** msg1 <=160 chars, references the gap, no forbidden phrases, no em-dashes, no !!!. Fail -> ONE corrective retry -> if still bad, 'draft_failed' event, no bad draft written.\n\n**Idempotent:** per-channel NOT EXISTS guard; lead-level poll guard avoids re-calling Claude.\n\n**Email note:** schema has no subject column, so email subject is folded into draft_body as 'Subject: ...'.\n\n**Set:** `Postgres \u00b7 warm_outreach` + `Anthropic API (x-api-key)`.",
        "height": 380, "width": 480},
     "id": "note", "name": "About", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [-960, -160]},
]

connections = {
    "Every 5 min": {"main": [[{"node": "Scored Leads To Draft", "type": "main", "index": 0}]]},
    "Scored Leads To Draft": {"main": [[{"node": "Expand To Channel Jobs", "type": "main", "index": 0}]]},
    "Expand To Channel Jobs": {"main": [[{"node": "Loop jobs", "type": "main", "index": 0}]]},
    "Loop jobs": {"main": [[], [{"node": "Draft (Claude)", "type": "main", "index": 0}]]},
    "Draft (Claude)": {"main": [[{"node": "Validate", "type": "main", "index": 0}]]},
    "Validate": {"main": [
        [{"node": "Save Drafts", "type": "main", "index": 0}],
        [{"node": "Draft Retry (corrective)", "type": "main", "index": 0}],
    ]},
    "Draft Retry (corrective)": {"main": [[{"node": "Validate Retry", "type": "main", "index": 0}]]},
    "Validate Retry": {"main": [
        [{"node": "Save Drafts", "type": "main", "index": 0}],
        [{"node": "Log Draft Failed", "type": "main", "index": 0}],
    ]},
    "Save Drafts": {"main": [[{"node": "Log Draft Event", "type": "main", "index": 0}]]},
    "Log Draft Event": {"main": [[{"node": "Jitter", "type": "main", "index": 0}]]},
    "Log Draft Failed": {"main": [[{"node": "Jitter", "type": "main", "index": 0}]]},
    "Jitter": {"main": [[{"node": "Loop jobs", "type": "main", "index": 0}]]},
}

workflow = {"name": "OPS-WO \u00b7 Draft Outreach", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "active": False, "pinData": {}, "meta": {"templatecredsSetupCompleted": False}}

out = ROOT / "shared" / "n8n-templates" / "draft_outreach.json"
out.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
print("wrote", out)
print("forbidden phrases embedded:", len(phrases))
print("sonnet sys chars:", len(sonnet_sys), "| opus sys chars:", len(opus_sys), "| email sys chars:", len(email_sys))
