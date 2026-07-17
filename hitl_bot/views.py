"""Interactive Discord components for the HITL bot.

Buttons are DynamicItems: their state (outreach_id / lead_id) lives in the custom_id, so
discord.py can reconstruct the handler after a bot or VPS restart — approvals keep working
on old messages without re-registering per-message views. DB calls are sync (psycopg), so
they run in an executor to avoid blocking the event loop."""
import asyncio
import re

import discord

import db


async def _run(func, *args):
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)


def _actor(interaction: discord.Interaction) -> str:
    u = interaction.user
    return f"{u.name}#{getattr(u, 'discriminator', '0')}" if u else "unknown"


REJECT_REASONS = [
    "Bad hook", "Missed the gap", "Sounds AI",
    "Wrong channel for this prospect", "Prospect actually not ICP", "Other",
]


# --------------------------------------------------------------------------- #
# Edit modal
# --------------------------------------------------------------------------- #
class EditModal(discord.ui.Modal, title="Edit draft"):
    def __init__(self, outreach_id: int, current_body: str):
        super().__init__()
        self.outreach_id = outreach_id
        self.body_input = discord.ui.TextInput(
            label="Approved message",
            style=discord.TextStyle.paragraph,
            default=current_body[:4000],
            max_length=4000,
        )
        self.add_item(self.body_input)

    async def on_submit(self, interaction: discord.Interaction):
        lead_id = await _run(db.approve, self.outreach_id, _actor(interaction), str(self.body_input.value))
        msg = "✏️ Edited & approved." if lead_id else "⚠️ Already actioned (not in draft state)."
        await interaction.response.send_message(msg, ephemeral=True)


# --------------------------------------------------------------------------- #
# Reject reason picker (ephemeral)
# --------------------------------------------------------------------------- #
class OtherReasonModal(discord.ui.Modal, title="Reject reason"):
    def __init__(self, outreach_id: int):
        super().__init__()
        self.outreach_id = outreach_id
        self.reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.short, max_length=200)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        lead_id = await _run(db.reject, self.outreach_id, _actor(interaction), str(self.reason.value))
        msg = "❌ Rejected." if lead_id else "⚠️ Already actioned."
        await interaction.response.send_message(msg, ephemeral=True)


class RejectReasonSelect(discord.ui.Select):
    def __init__(self, outreach_id: int):
        self.outreach_id = outreach_id
        super().__init__(
            placeholder="Why reject?",
            options=[discord.SelectOption(label=r) for r in REJECT_REASONS],
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        reason = self.values[0]
        if reason == "Other":
            await interaction.response.send_modal(OtherReasonModal(self.outreach_id))
            return
        lead_id = await _run(db.reject, self.outreach_id, _actor(interaction), reason)
        msg = f"❌ Rejected: {reason}" if lead_id else "⚠️ Already actioned."
        await interaction.response.send_message(msg, ephemeral=True)


class RejectReasonView(discord.ui.View):
    def __init__(self, outreach_id: int):
        super().__init__(timeout=120)
        self.add_item(RejectReasonSelect(outreach_id))


# --------------------------------------------------------------------------- #
# Persistent buttons (DynamicItem — survive restarts)
# --------------------------------------------------------------------------- #
class ApproveButton(discord.ui.DynamicItem[discord.ui.Button], template=r"hitl:approve:(?P<id>\d+)"):
    def __init__(self, outreach_id: int):
        self.outreach_id = outreach_id
        super().__init__(discord.ui.Button(label="Approve", emoji="✅",
                                           style=discord.ButtonStyle.success,
                                           custom_id=f"hitl:approve:{outreach_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        lead_id = await _run(db.approve, self.outreach_id, _actor(interaction))
        msg = "✅ Approved." if lead_id else "⚠️ Already actioned."
        await interaction.response.send_message(msg, ephemeral=True)


class EditButton(discord.ui.DynamicItem[discord.ui.Button], template=r"hitl:edit:(?P<id>\d+)"):
    def __init__(self, outreach_id: int):
        self.outreach_id = outreach_id
        super().__init__(discord.ui.Button(label="Edit", emoji="✏️",
                                           style=discord.ButtonStyle.primary,
                                           custom_id=f"hitl:edit:{outreach_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        current = await _run(db_fetch_body, self.outreach_id)
        if current is None:
            await interaction.response.send_message("⚠️ Already actioned.", ephemeral=True)
            return
        await interaction.response.send_modal(EditModal(self.outreach_id, current))


class RejectButton(discord.ui.DynamicItem[discord.ui.Button], template=r"hitl:reject:(?P<id>\d+)"):
    def __init__(self, outreach_id: int):
        self.outreach_id = outreach_id
        super().__init__(discord.ui.Button(label="Reject", emoji="❌",
                                           style=discord.ButtonStyle.danger,
                                           custom_id=f"hitl:reject:{outreach_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pick a reason:", view=RejectReasonView(self.outreach_id), ephemeral=True)


class SkipButton(discord.ui.DynamicItem[discord.ui.Button], template=r"hitl:skip:(?P<lead>\d+)"):
    def __init__(self, lead_id: int):
        self.lead_id = lead_id
        super().__init__(discord.ui.Button(label="Skip Lead", emoji="⏭️",
                                           style=discord.ButtonStyle.secondary,
                                           custom_id=f"hitl:skip:{lead_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["lead"]))

    async def callback(self, interaction: discord.Interaction):
        n = await _run(db.skip_lead, self.lead_id, _actor(interaction))
        await interaction.response.send_message(f"⏭️ Skipped lead ({n} draft(s)).", ephemeral=True)


class BulkWarmButton(discord.ui.DynamicItem[discord.ui.Button], template=r"hitl:bulkwarm"):
    def __init__(self):
        super().__init__(discord.ui.Button(label="Approve Next 10 Warm", emoji="⚡",
                                           style=discord.ButtonStyle.success,
                                           custom_id="hitl:bulkwarm"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        names = await _run(db.bulk_approve_warm, _actor(interaction), 10)
        if not names:
            await interaction.response.send_message("No warm-queue drafts to bulk-approve.", ephemeral=True)
            return
        listed = ", ".join(names[:20])
        await interaction.response.send_message(f"✅✅ Approved {len(names)} warm drafts: {listed}", ephemeral=True)


def db_fetch_body(outreach_id: int):
    """Return draft_body if the row is still in 'draft', else None (helper for Edit)."""
    with db._conn() as c, c.cursor() as cur:
        cur.execute("SELECT draft_body FROM lead_outreach WHERE id = %s AND status = 'draft'", (outreach_id,))
        row = cur.fetchone()
        return row[0] if row else None


DYNAMIC_ITEMS = [ApproveButton, EditButton, RejectButton, SkipButton, BulkWarmButton]


def build_view(draft: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ApproveButton(draft["id"]))
    view.add_item(EditButton(draft["id"]))
    view.add_item(RejectButton(draft["id"]))
    view.add_item(SkipButton(draft["lead_id"]))
    if draft.get("tier") == "warm":  # hot (20+) is never bulk-approvable — rule, not config
        view.add_item(BulkWarmButton())
    return view
