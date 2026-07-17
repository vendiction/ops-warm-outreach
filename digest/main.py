"""Phase 8 digest service.

Two scheduled jobs (APScheduler, in-process):
  - Daily 08:00  -> build the digest from the analytics views, post to Discord.
  - Sunday 21:00 -> build a weekly PDF (reportlab), post a note + attach to Discord.

build_daily_digest() and build_weekly_pdf() are pure enough to test against a live DB
without the scheduler. Reads only the v_* analytics views.
"""
import os
import io
import logging
from datetime import date

import httpx
from psycopg_pool import ConnectionPool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("digest")

DISCORD_WEBHOOK = os.getenv("DISCORD_DIGEST_WEBHOOK", "")
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=3, open=True)
    return _pool


def _q1(sql, default=None):
    with _get_pool().connection() as c, c.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return row if row else default


def _qall(sql):
    with _get_pool().connection() as c, c.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def build_daily_digest() -> str:
    today = date.today().isoformat()

    # Yesterday's pipeline events, pivoted.
    ev = dict(_qall(
        "SELECT event_type, SUM(n)::int FROM v_daily_pipeline "
        "WHERE day = CURRENT_DATE - 1 GROUP BY 1"
    ) or [])
    sourced = ev.get("source", 0)
    enriched = ev.get("enrich", 0)
    scored = ev.get("score", 0)
    drafts = ev.get("draft", 0)

    # Audit activity yesterday.
    audit = _q1(
        "SELECT COALESCE(SUM(n) FILTER (WHERE audit_status='complete'),0)::int, "
        "COALESCE(SUM(n) FILTER (WHERE audit_status='failed'),0)::int "
        "FROM v_audit_health WHERE day = CURRENT_DATE - 1", (0, 0))
    audits_done, audits_failed = audit

    # HITL queue depth.
    hitl = _q1("SELECT COALESCE(SUM(drafts_waiting),0)::int, COALESCE(MAX(oldest_wait_hours),0) FROM v_hitl_queue", (0, 0))
    queue_n, queue_wait = hitl

    # Sends + replies yesterday.
    sends = _q1(
        "SELECT COALESCE(SUM(sent),0)::int, COALESCE(SUM(replied),0)::int, "
        "COALESCE(SUM(interested),0)::int, COALESCE(SUM(not_interested),0)::int "
        "FROM v_channel_reply_rates WHERE sent_day = CURRENT_DATE - 1", (0, 0, 0, 0))
    sent, replied, interested, not_interested = sends

    # 7-day audit success + inbox pool.
    succ = _q1("SELECT success_pct FROM v_audit_success_7d", (None,))[0]
    inbox = _q1("SELECT COUNT(*)::int, COUNT(*) FILTER (WHERE in_cooldown)::int FROM v_inbox_health", (0, 0))
    inbox_used, inbox_cooling = inbox

    succ_str = f"{succ}%" if succ is not None else "n/a"
    lines = [
        f"🌅 **OPS-WARM-OUTREACH — Daily Digest — {today}**",
        "",
        f"📥 Sourced yesterday: {sourced}",
        f"🧬 Enriched: {enriched}",
        f"⚙️ Audits completed: {audits_done} · failed: {audits_failed}",
        f"📊 Scored: {scored}",
        f"✍️ Drafts created: {drafts}",
        f"🎛️ In HITL queue: {queue_n} (oldest {queue_wait}h)",
        f"📤 Sent: {sent} · 💬 Replies: {replied} (interested {interested} / not {not_interested})",
        "",
        "🚦 Health:",
        f"  • Audit success rate (7d): {succ_str}",
        f"  • Inbox pool activity (7d): {inbox_used} used, {inbox_cooling} cooling down",
    ]
    return "\n".join(lines)


def build_weekly_pdf(path: str = "/tmp/weekly_report.pdf") -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    funnel = _qall(
        "SELECT COALESCE(SUM(sourced),0), COALESCE(SUM(enriched),0), COALESCE(SUM(audited),0), "
        "COALESCE(SUM(qualified),0), COALESCE(SUM(contacted),0), COALESCE(SUM(interested_replies),0) "
        "FROM v_conversion_funnel WHERE source_day >= CURRENT_DATE - 7")
    f = funnel[0] if funnel else (0, 0, 0, 0, 0, 0)
    rejects = _qall("SELECT rejected_reason, n FROM v_reject_reasons LIMIT 5")

    c = canvas.Canvas(path, pagesize=letter)
    w, h = letter
    y = h - inch
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, f"OPS-WARM-OUTREACH — Weekly Report — {date.today().isoformat()}")
    y -= 0.4 * inch
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Executive summary")
    y -= 0.28 * inch
    labels = ["Sourced", "Enriched", "Audited", "Qualified (>=15)", "Contacted", "Interested replies"]
    for label, val in zip(labels, f):
        c.drawString(inch + 0.2 * inch, y, f"{label}: {val}")
        y -= 0.24 * inch
    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(inch, y, "Top rejection reasons (prompt-tuning signal)")
    y -= 0.28 * inch
    c.setFont("Helvetica", 11)
    if rejects:
        for reason, n in rejects:
            c.drawString(inch + 0.2 * inch, y, f"{reason}: {n}")
            y -= 0.24 * inch
    else:
        c.drawString(inch + 0.2 * inch, y, "None yet.")
    c.showPage()
    c.save()
    return path


def post_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        log.warning("no DISCORD_DIGEST_WEBHOOK set; digest not posted:\n%s", content)
        return
    try:
        httpx.post(DISCORD_WEBHOOK, json={"content": content[:1900]}, timeout=15)
    except Exception as e:
        log.error("discord post failed: %s", e)


def post_discord_pdf(path: str, note: str) -> None:
    if not DISCORD_WEBHOOK:
        log.warning("no webhook; weekly PDF at %s", path)
        return
    try:
        with open(path, "rb") as fh:
            httpx.post(DISCORD_WEBHOOK, data={"content": note},
                       files={"file": ("weekly_report.pdf", fh, "application/pdf")}, timeout=30)
    except Exception as e:
        log.error("discord pdf post failed: %s", e)


def run_daily():
    post_discord(build_daily_digest())


def run_weekly():
    path = build_weekly_pdf()
    post_discord_pdf(path, "📈 Weekly report for Jon")


def main():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    tz = os.getenv("DIGEST_TZ", "Asia/Manila")
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(run_daily, CronTrigger(hour=8, minute=0), id="daily_digest")
    sched.add_job(run_weekly, CronTrigger(day_of_week="sun", hour=21, minute=0), id="weekly_report")
    log.info("digest scheduler starting (tz=%s): daily 08:00, weekly Sun 21:00", tz)
    sched.start()


if __name__ == "__main__":
    main()
