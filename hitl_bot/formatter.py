"""Format a draft row into a Discord embed. No live Discord needed to build the embed
object, so the field assembly is unit-testable."""
import os
import discord

_TIER_COLOR = {
    "hot": 0xE74C3C,     # red accent
    "warm": 0x3498DB,    # blue
    "cold": 0x95A5A6,    # grey
    "unknown": 0x95A5A6,
}
_CHANNEL_LABEL = {
    "dm_ig": "IG DM", "dm_linkedin": "LinkedIn DM", "dm_fb": "Facebook DM", "cold_email": "Cold Email",
}
_METABASE_BASE = os.getenv("METABASE_BASE_URL", "").rstrip("/")


def build_embed(draft: dict) -> discord.Embed:
    tier = draft.get("tier", "unknown")
    score = draft.get("qualification_score")
    company = draft.get("company_name") or f"Lead {draft['lead_id']}"
    channel_label = _CHANNEL_LABEL.get(draft["channel"], draft["channel"])
    char_count = draft.get("draft_char_count") or len(draft.get("draft_body") or "")

    embed = discord.Embed(
        title=f"📩 Draft — {company}  (score {score if score is not None else '?'}, {tier})",
        color=_TIER_COLOR.get(tier, 0x95A5A6),
    )
    embed.add_field(
        name="Context",
        value=f"{channel_label} · Step {draft['sequence_step']} · {char_count} chars · model `{draft.get('draft_model') or '?'}`",
        inline=False,
    )
    gap = draft.get("gap_summary")
    if gap:
        embed.add_field(name="Gap", value=gap[:1000], inline=False)
    embed.add_field(name="Draft", value=(draft.get("draft_body") or "")[:1800] or "(empty)", inline=False)

    footer = f"lead #{draft['lead_id']} · outreach #{draft['id']}"
    if _METABASE_BASE:
        # Deep-link into the lead's row (question id configured per install).
        embed.add_field(
            name="Record",
            value=f"[Open in Metabase]({_METABASE_BASE}/question?lead_id={draft['lead_id']})",
            inline=False,
        )
    embed.set_footer(text=footer)
    return embed
