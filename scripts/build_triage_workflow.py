#!/usr/bin/env python3
"""Generates shared/n8n-templates/triage_email_replies.json with the reply-triage system
prompt embedded VERBATIM from prompts/reply_triage_haiku.md."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
md = (ROOT / "prompts" / "reply_triage_haiku.md").read_text(encoding="utf-8")
system_prompt = md[md.index("## System"):].strip()


def lit(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


prep_js = (
    "// Pull sender + text from the IMAP message, embed the triage system prompt.\n"
    "const msg = $json;\n"
    "const from = (msg.from && msg.from.value && msg.from.value[0] && msg.from.value[0].address) "
    "|| msg.from || msg.fromEmail || '';\n"
    "const text = (msg.text || msg.textPlain || msg.snippet || '').toString().slice(0, 4000);\n"
    f"const SYSTEM = `{lit(system_prompt)}`;\n"
    "return [{ json: { from_email: String(from).toLowerCase().trim(), reply_text: text, system: SYSTEM } }];"
)

parse_js = (
    "const body = $json;\n"
    "let text=''; try { text=(body.content||[]).filter(b=>b.type==='text').map(b=>b.text).join(''); } catch(e){}\n"
    "let parsed; try { parsed=JSON.parse((text||'').replace(/```json|```/g,'').trim()); } catch(e){ parsed={classification:'unclear',reasoning:'parse_failed',urgency:'normal'}; }\n"
    "const valid=['interested','objection','not_interested','unclear','auto_reply'];\n"
    "if(!valid.includes(parsed.classification)) parsed.classification='unclear';\n"
    "if(!['high','normal','low'].includes(parsed.urgency)) parsed.urgency='normal';\n"
    "return [{ json: { from_email: $('Prep Reply').item.json.from_email, reply_text: $('Prep Reply').item.json.reply_text, classification: parsed.classification, reasoning: (parsed.reasoning||'').slice(0,300), urgency: parsed.urgency } }];"
)

anthropic_cred = {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "Anthropic API (x-api-key)"}}
pg_cred = {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}}

nodes = [
    {"parameters": {"mailbox": "INBOX", "postProcessAction": "read",
        "format": "simple", "options": {}},
     "id": "imap", "name": "New Reply (IMAP)", "type": "n8n-nodes-base.emailReadImap",
     "typeVersion": 2, "position": [-960, 300],
     "credentials": {"imap": {"id": "REPLACE_ME", "name": "Cold Email IMAP"}}},
    {"parameters": {"jsCode": prep_js},
     "id": "prep", "name": "Prep Reply", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-740, 300]},
    {"parameters": {"operation": "executeQuery",
        "query": "SELECT id AS lead_id FROM leads WHERE LOWER(founder_email) = $1 LIMIT 1;",
        "options": {"queryReplacement": "={{ [$json.from_email] }}"}},
     "id": "pg-lead", "name": "Match Lead", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
     "position": [-520, 300], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "anthropic-version", "value": "2023-06-01"},
            {"name": "content-type", "value": "application/json"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ { model: 'claude-haiku-4-5-20251001', max_tokens: 200, temperature: 0, system: $('Prep Reply').item.json.system, messages: [ { role: 'user', content: $('Prep Reply').item.json.reply_text } ] } }}",
        "options": {"timeout": 20000}},
     "id": "haiku", "name": "Classify (Haiku)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [-300, 300], "credentials": anthropic_cred, "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 3000},
    {"parameters": {"jsCode": parse_js},
     "id": "parse", "name": "Parse Classification", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-80, 300]},
    {"parameters": {"operation": "executeQuery",
        "query": "-- Attach the reply to the most recent sent cold-email for this lead.\nWITH tgt AS (\n  SELECT lo.id, lo.lead_id FROM lead_outreach lo\n  JOIN leads l ON l.id = lo.lead_id\n  WHERE LOWER(l.founder_email) = $1 AND lo.channel='cold_email' AND lo.status='sent'\n  ORDER BY lo.sent_at DESC LIMIT 1\n)\nUPDATE lead_outreach lo\nSET reply_body=$2, reply_received_at=NOW(), reply_classification=$3::reply_classification_enum,\n    reply_reasoning=$4, updated_at=NOW()\nFROM tgt WHERE lo.id = tgt.id\nRETURNING lo.lead_id;",
        "options": {"queryReplacement": "={{ [$json.from_email, $json.reply_text, $json.classification, $json.reasoning] }}"}},
     "id": "pg-update", "name": "Save Reply", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
     "position": [140, 300], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "INSERT INTO outreach_events (lead_id, event_type, event_data, actor)\nSELECT lead_id, 'reply', $2::jsonb, 'system' FROM leads WHERE LOWER(founder_email)=$1 LIMIT 1;",
        "options": {"queryReplacement": "={{ [$('Parse Classification').item.json.from_email, JSON.stringify({ classification: $('Parse Classification').item.json.classification, urgency: $('Parse Classification').item.json.urgency }) ] }}"}},
     "id": "pg-event", "name": "Log Reply Event", "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
     "position": [360, 300], "credentials": pg_cred, "onError": "continueRegularOutput"},
    {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"},
        "conditions": [{"leftValue": "={{ $('Parse Classification').item.json.classification }}", "rightValue": "interested", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
     "id": "if", "name": "Interested?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [580, 300]},
    {"parameters": {"method": "POST", "url": "={{ $env.DISCORD_HOTLEAD_WEBHOOK }}",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ { content: '🔥 **Interested email reply** from ' + $('Parse Classification').item.json.from_email + '\\n> ' + $('Parse Classification').item.json.reply_text.slice(0,300) + '\\n_' + $('Parse Classification').item.json.reasoning + '_ · urgency: ' + $('Parse Classification').item.json.urgency } }}",
        "options": {}},
     "id": "discord", "name": "Ping Hot-Lead Channel", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [800, 220], "onError": "continueRegularOutput"},
    {"parameters": {"content": "## Triage Email Replies (automated)\nIMAP trigger on the cold-email inbox. For each inbound reply: match the sender to a lead, classify with Haiku (prompt embedded verbatim from prompts/reply_triage_haiku.md), attach to the most recent sent cold-email, log a 'reply' event, and ping the hot-lead channel if **interested**. A human then takes over the conversation (zero automated replies to prospects).\n\n**Set:** `Cold Email IMAP` + `Postgres · warm_outreach` + `Anthropic API` creds; env `DISCORD_HOTLEAD_WEBHOOK`.\n\nDM replies are handled by the send console's paste-a-reply action (same classifier).",
        "height": 280, "width": 470},
     "id": "note", "name": "About", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [-740, -40]},
]

connections = {
    "New Reply (IMAP)": {"main": [[{"node": "Prep Reply", "type": "main", "index": 0}]]},
    "Prep Reply": {"main": [[{"node": "Match Lead", "type": "main", "index": 0}]]},
    "Match Lead": {"main": [[{"node": "Classify (Haiku)", "type": "main", "index": 0}]]},
    "Classify (Haiku)": {"main": [[{"node": "Parse Classification", "type": "main", "index": 0}]]},
    "Parse Classification": {"main": [[{"node": "Save Reply", "type": "main", "index": 0}]]},
    "Save Reply": {"main": [[{"node": "Log Reply Event", "type": "main", "index": 0}]]},
    "Log Reply Event": {"main": [[{"node": "Interested?", "type": "main", "index": 0}]]},
    "Interested?": {"main": [[{"node": "Ping Hot-Lead Channel", "type": "main", "index": 0}], []]},
}

wf = {"name": "OPS-WO \u00b7 Triage Email Replies", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1"}, "active": False, "pinData": {}, "meta": {"templatecredsSetupCompleted": False}}
out = ROOT / "shared" / "n8n-templates" / "triage_email_replies.json"
out.write_text(json.dumps(wf, indent=2), encoding="utf-8")
print("wrote", out, "| prompt chars:", len(system_prompt))
