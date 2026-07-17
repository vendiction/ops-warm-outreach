#!/usr/bin/env python3
"""Generates shared/n8n-templates/score_qualified_audits.json, embedding the scoring
system prompt VERBATIM from prompts/scoring_haiku.md so the workflow can't drift from
the canonical prompt. Re-run this whenever scoring_haiku.md changes."""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
prompt_md = (ROOT / "prompts" / "scoring_haiku.md").read_text(encoding="utf-8")

# Take everything from the "## System" heading onward (drops the version/meta header).
idx = prompt_md.index("## System")
system_prompt = prompt_md[idx:].strip()


def js_template_literal(s: str) -> str:
    # Escape for embedding inside a JS backtick template literal.
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


compose_js = (
    "const r = $('Loop').item.json;\n"
    "const payload = {\n"
    "  company_name: r.company_name, domain: r.domain, icp_tier: r.icp_tier,\n"
    "  traffic_monthly: (r.traffic_estimate ?? null),\n"
    "  tech_stack: r.tech_stack || {},\n"
    "  recent_social_posts: r.recent_social_posts || [],\n"
    "  audit: {\n"
    "    welcome_email_received: r.welcome_email_received,\n"
    "    welcome_has_cta: r.welcome_has_cta,\n"
    "    abandoned_cart_count: r.abandoned_cart_count,\n"
    "    abandoned_application_followup_count: r.abandoned_application_followup_count,\n"
    "    first_recovery_delay_hours: r.first_recovery_delay_hours,\n"
    "    discount_offered: r.discount_offered,\n"
    "    total_emails_received_72h: r.total_emails_received_72h,\n"
    "    deliverability_signal: r.deliverability_signal,\n"
    "    gap_summary: r.gap_summary\n"
    "  }\n"
    "};\n"
    "// SYSTEM prompt embedded verbatim from prompts/scoring_haiku.md (built by scripts/build_scoring_workflow.py — do not hand-edit)\n"
    f"const SYSTEM = `{js_template_literal(system_prompt)}`;\n"
    "return [{ json: { lead_id: r.lead_id, payload, system: SYSTEM } }];"
)

parse_js = (
    "// Parse Haiku's JSON, validate the rubric schema. Throw on invalid so the error\n"
    "// output routes to the score_failed logger (never force a default score).\n"
    "const body = $json;\n"
    "let text = '';\n"
    "try { text = (body.content || []).filter(b => b.type === 'text').map(b => b.text).join(''); } catch (e) {}\n"
    "let parsed;\n"
    "try { parsed = JSON.parse((text || '').replace(/```json|```/g, '').trim()); }\n"
    "catch (e) { throw new Error('malformed_json_from_haiku'); }\n"
    "const ss = parsed.subscores || {};\n"
    "for (const k of ['revenue','margin','list','growth','authority']) {\n"
    "  const v = ss[k];\n"
    "  if (!Number.isInteger(v) || v < 1 || v > 5) throw new Error('bad_subscore_' + k);\n"
    "}\n"
    "const total = parsed.total;\n"
    "if (!Number.isInteger(total) || total < 5 || total > 25) throw new Error('bad_total');\n"
    "const sum = ['revenue','margin','list','growth','authority'].reduce((a,k)=>a+ss[k],0);\n"
    "if (sum !== total) throw new Error('total_mismatch_' + sum + '_vs_' + total);\n"
    "const queue = total >= 20 ? 'hot' : total >= 15 ? 'warm' : total >= 10 ? 'cold' : 'archive';\n"
    "return [{ json: { lead_id: $('Loop').item.json.lead_id, subscores: ss, total, reasoning: (parsed.reasoning || ''), queue } }];"
)

nodes = [
    {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}},
     "id": "sched", "name": "Every minute", "type": "n8n-nodes-base.scheduleTrigger",
     "typeVersion": 1.2, "position": [-960, 300]},
    {"parameters": {"operation": "executeQuery",
        "query": "SELECT l.id AS lead_id, l.company_name, l.domain, l.icp_tier, l.founder_name,\n       e.traffic_estimate, e.tech_stack, e.recent_social_posts,\n       a.welcome_email_received, a.welcome_has_cta, a.abandoned_cart_count,\n       a.abandoned_application_followup_count, a.first_recovery_delay_hours,\n       a.discount_offered, a.total_emails_received_72h, a.deliverability_signal, a.gap_summary\nFROM lead_audits a\nJOIN leads l ON l.id = a.lead_id\nLEFT JOIN lead_enrichment e ON e.lead_id = l.id\nWHERE a.audit_status = 'complete'\n  AND l.qualification_score IS NULL\n  AND l.is_archived = FALSE\nORDER BY a.completed_at ASC NULLS LAST\nLIMIT 20;",
        "options": {}},
     "id": "pg-select", "name": "Audits To Score", "type": "n8n-nodes-base.postgres",
     "typeVersion": 2.6, "position": [-740, 300],
     "credentials": {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}}},
    {"parameters": {"batchSize": 1, "options": {}},
     "id": "loop", "name": "Loop", "type": "n8n-nodes-base.splitInBatches",
     "typeVersion": 3, "position": [-520, 300]},
    {"parameters": {"jsCode": compose_js},
     "id": "compose", "name": "Compose Payload", "type": "n8n-nodes-base.code",
     "typeVersion": 2, "position": [-300, 200]},
    {"parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "anthropic-version", "value": "2023-06-01"},
            {"name": "content-type", "value": "application/json"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ { model: 'claude-haiku-4-5-20251001', max_tokens: 400, temperature: 0, system: $json.system, messages: [ { role: 'user', content: JSON.stringify($json.payload) } ] } }}",
        "options": {"timeout": 30000}},
     "id": "haiku", "name": "Haiku Score", "type": "n8n-nodes-base.httpRequest",
     "typeVersion": 4.2, "position": [-80, 200],
     "credentials": {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "Anthropic API (x-api-key)"}},
     "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 3000},
    {"parameters": {"jsCode": parse_js},
     "id": "parse", "name": "Parse & Validate", "type": "n8n-nodes-base.code",
     "typeVersion": 2, "position": [140, 200], "onError": "continueErrorOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "UPDATE leads SET\n  qualification_score = $2,\n  qualification_subscores = $3::jsonb,\n  qualification_reasoning = $4,\n  is_archived = CASE WHEN $2 < 10 THEN TRUE ELSE is_archived END,\n  archive_reason = CASE WHEN $2 < 10 THEN 'score below threshold: ' || $2 || '/25' ELSE archive_reason END,\n  source_metadata = source_metadata || jsonb_build_object('queue', $5::text),\n  updated_at = NOW()\nWHERE id = $1;",
        "options": {"queryReplacement": "={{ [$json.lead_id, $json.total, JSON.stringify($json.subscores), $json.reasoning, $json.queue] }}"}},
     "id": "save", "name": "Save Score", "type": "n8n-nodes-base.postgres",
     "typeVersion": 2.6, "position": [360, 120],
     "credentials": {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}},
     "onError": "continueRegularOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "INSERT INTO outreach_events (lead_id, event_type, event_data, actor)\nVALUES ($1, 'score', $2::jsonb, 'system');",
        "options": {"queryReplacement": "={{ [$json.lead_id, JSON.stringify({ score: $json.total, queue: $json.queue, subscores: $json.subscores }) ] }}"}},
     "id": "event", "name": "Log Score Event", "type": "n8n-nodes-base.postgres",
     "typeVersion": 2.6, "position": [580, 120],
     "credentials": {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}},
     "onError": "continueRegularOutput"},
    {"parameters": {"operation": "executeQuery",
        "query": "INSERT INTO outreach_events (lead_id, event_type, event_data, actor)\nVALUES ($1, 'score_failed', $2::jsonb, 'system');",
        "options": {"queryReplacement": "={{ [$('Loop').item.json.lead_id, JSON.stringify({ error: ($json.error && $json.error.message) ? $json.error.message : 'score_parse_failed' }) ] }}"}},
     "id": "event-fail", "name": "Log Score Failed", "type": "n8n-nodes-base.postgres",
     "typeVersion": 2.6, "position": [360, 320],
     "credentials": {"postgres": {"id": "REPLACE_ME", "name": "Postgres \u00b7 warm_outreach"}},
     "onError": "continueRegularOutput"},
    {"parameters": {"amount": 1, "unit": "seconds"},
     "id": "jitter", "name": "Jitter", "type": "n8n-nodes-base.wait",
     "typeVersion": 1.1, "position": [780, 200]},
    {"parameters": {"content": "## Score Qualified Audits\nEvery minute: pulls completed audits whose lead has no score yet, sends enrichment+audit to Haiku with the rubric (embedded verbatim from prompts/scoring_haiku.md), writes score + 5 subscores + reasoning, routes by band.\n\n**Routing** is implicit in the score (Phase 5 selects by band). Only <10 writes is_archived. The queue label (hot/warm/cold) is stored in source_metadata for visibility.\n\n**Malformed Haiku JSON** routes to the error output -> 'score_failed' event; the lead stays unscored and is retried next run (never forced to a default score).\n\n**Set:** `Postgres \u00b7 warm_outreach` + `Anthropic API (x-api-key)` credentials.\n**Idempotent:** re-runs skip already-scored leads (qualification_score IS NULL guard).",
        "height": 340, "width": 470},
     "id": "note", "name": "About", "type": "n8n-nodes-base.stickyNote",
     "typeVersion": 1, "position": [-740, -120]},
]

connections = {
    "Every minute": {"main": [[{"node": "Audits To Score", "type": "main", "index": 0}]]},
    "Audits To Score": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},
    "Loop": {"main": [[], [{"node": "Compose Payload", "type": "main", "index": 0}]]},
    "Compose Payload": {"main": [[{"node": "Haiku Score", "type": "main", "index": 0}]]},
    "Haiku Score": {"main": [[{"node": "Parse & Validate", "type": "main", "index": 0}]]},
    "Parse & Validate": {"main": [
        [{"node": "Save Score", "type": "main", "index": 0}],
        [{"node": "Log Score Failed", "type": "main", "index": 0}],
    ]},
    "Save Score": {"main": [[{"node": "Log Score Event", "type": "main", "index": 0}]]},
    "Log Score Event": {"main": [[{"node": "Jitter", "type": "main", "index": 0}]]},
    "Log Score Failed": {"main": [[{"node": "Jitter", "type": "main", "index": 0}]]},
    "Jitter": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},
}

workflow = {"name": "OPS-WO \u00b7 Score Qualified Audits", "nodes": nodes,
            "connections": connections, "settings": {"executionOrder": "v1"},
            "active": False, "pinData": {}, "meta": {"templatecredsSetupCompleted": False}}

out = ROOT / "shared" / "n8n-templates" / "score_qualified_audits.json"
out.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
print("wrote", out)
print("embedded system prompt chars:", len(system_prompt))
