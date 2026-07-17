"""HITL bot entrypoint.

Registers the persistent DynamicItem buttons, then every 30s posts up to 5 un-posted
drafts (hottest first) to the configured channel and marks them posted so they're never
re-posted. discord.py handles reconnects; deploy with restart: unless-stopped."""
import asyncio
import logging
import os

import discord
from discord.ext import tasks

import db
import views
from formatter import build_embed

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("hitl_bot")

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
HITL_CHANNEL_ID = int(os.environ["DISCORD_HITL_CHANNEL_ID"])
POLL_SECONDS = int(os.getenv("HITL_POLL_SECONDS", "30"))
BATCH = int(os.getenv("HITL_BATCH", "5"))


class HITLBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()  # no message-content intent needed; buttons only
        super().__init__(intents=intents)

    async def setup_hook(self):
        # Register dynamic buttons so old messages' buttons work after a restart.
        for item in views.DYNAMIC_ITEMS:
            self.add_dynamic_items(item)
        self.poll_drafts.start()

    async def on_ready(self):
        log.info("logged in as %s", self.user)

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_drafts(self):
        try:
            channel = self.get_channel(HITL_CHANNEL_ID) or await self.fetch_channel(HITL_CHANNEL_ID)
        except Exception as e:
            log.error("cannot reach HITL channel %s: %s", HITL_CHANNEL_ID, e)
            return
        try:
            drafts = await asyncio.get_running_loop().run_in_executor(None, db.fetch_unposted_drafts, BATCH)
        except Exception as e:
            log.error("db fetch failed: %s", e)
            return

        posted = []
        for draft in drafts:
            try:
                await channel.send(embed=build_embed(draft), view=views.build_view(draft))
                posted.append(draft["id"])
            except Exception as e:
                log.error("failed to post draft %s: %s", draft["id"], e)
        if posted:
            try:
                await asyncio.get_running_loop().run_in_executor(None, db.mark_posted, posted)
                log.info("posted %d drafts", len(posted))
            except Exception as e:
                log.error("mark_posted failed for %s: %s", posted, e)

    @poll_drafts.before_loop
    async def before_poll(self):
        await self.wait_until_ready()


def main():
    HITLBot().run(TOKEN)


if __name__ == "__main__":
    main()
