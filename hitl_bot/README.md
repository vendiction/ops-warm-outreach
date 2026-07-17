# HITL Bot — Phase 6

Discord review surface. Posts each `draft` from `lead_outreach` to a channel with
Approve / Edit / Reject / Skip buttons (plus "Approve Next 10 Warm" on warm drafts), and
writes the decision back to Postgres. Buttons are persistent, so they keep working after a
bot or VPS restart.

---

## Create a brand-new bot + token (do this once)

This build uses its **own dedicated bot** — don't reuse an existing FC bot token.

1. **Create the application.** Go to https://discord.com/developers/applications → **New
   Application** → name it e.g. `OPS-WO HITL`. → **Create**.
2. **Add the bot.** Left sidebar → **Bot** → (a bot user is created automatically on newer
   portals; if not, **Add Bot**). Set an avatar/name if you like.
3. **Get the token.** On the **Bot** page → **Reset Token** → **Copy**. This is
   `DISCORD_BOT_TOKEN`. You see it once — paste it straight into `.env`. Never commit it.
4. **Intents.** This bot only uses buttons, so it needs **no privileged intents**. Leave
   Message Content / Presence / Server Members **off**.
5. **Invite it to your server with least privilege.** Sidebar → **OAuth2** → **URL
   Generator**:
   - Scopes: `bot`
   - Bot Permissions: **View Channels**, **Send Messages**, **Embed Links**, **Read Message
     History** (that's all it needs — no admin, no manage).
   - Copy the generated URL, open it, pick your server, authorize.
6. **Get the channel ID.** In Discord: User Settings → Advanced → enable **Developer Mode**.
   Right-click the review channel → **Copy Channel ID**. This is `DISCORD_HITL_CHANNEL_ID`.
   Make sure the bot's role can see and post in that channel.

Put both values in `.env`:

```
DISCORD_BOT_TOKEN=...          # from step 3
DISCORD_HITL_CHANNEL_ID=...    # from step 6
DATABASE_URL=postgres://...    # same warm_outreach DB
METABASE_BASE_URL=https://...  # optional, enables "Open in Metabase" link
```

> If you'd rather keep it fully separate from the FC Discord, invite this bot to a dedicated
> server or a private category only Julia + Jon can see.

---

## Run

Apply the migration that adds the flag the bot needs, then start it:

```bash
psql "$DATABASE_URL" -f ../db/migrations/002_hitl_posted_flag.sql

# local
pip install -r requirements.txt && python main.py

# docker (add restart: unless-stopped in docker-compose)
docker build -t ops-wo-hitl-bot . && docker run --env-file ../.env ops-wo-hitl-bot
```

## What Julia sees

Each draft posts as an embed: company + score + tier (color-coded: hot=red, warm=blue,
cold=grey), channel + step + char count + model, the gap, and the full draft body.

- **✅ Approve** — status → `approved`, `approved_body` = draft, records who/when.
- **✏️ Edit** — modal prefilled with the draft; saving stores the rewrite in `approved_body`
  (`draft_body` is left untouched so we can measure edit rate).
- **❌ Reject** — pick a reason (Bad hook / Missed the gap / Sounds AI / Wrong channel / Not
  ICP / Other→freeform); stored in `rejected_reason` for weekly prompt tuning.
- **⏭️ Skip Lead** — marks all of that lead's remaining drafts `skipped`.
- **✅✅ Approve Next 10 Warm** — only shows on warm drafts. **Hot (score 20+) is never
  bulk-approvable — a rule enforced in SQL, not a config toggle.**

## Notes

- Poll: every 30s, posts up to 5 un-posted drafts (hottest first), marks them `posted_to_hitl`
  so nothing double-posts.
- Persistent buttons via `DynamicItem` (state in `custom_id`) — old messages stay actionable
  after a restart; no per-message re-registration.
- All transitions guard on `status = 'draft'`, so a double-click / stale button reports
  "already actioned" instead of clobbering a decision.
- No privileged intents; DB calls run in an executor so they never block the gateway.

## Testing

`db.py` is pure Postgres (no Discord import) and is unit-tested against a live DB — approve,
reject, skip, and warm-only bulk-approve transitions. `formatter.build_embed` and
`views.build_view` construct without a live connection.
