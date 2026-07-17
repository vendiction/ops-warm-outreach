# Forbidden Phrases — Draft Validator Blocklist

Used in: Phase 5 (draft validation)

Any draft body containing (case-insensitive) any phrase below is rejected before hitting the DB.
Retry once with a corrective note, then log + skip if it fails again.

## Fake compliments / AI tells

- Love your recent post
- Love your content
- Your content is amazing
- Great post about
- Hope this finds you well
- I hope you're doing well
- Just wanted to reach out
- I wanted to reach out
- I came across your profile
- I noticed you're
- I saw that you
- Reaching out because
- Big fan of

## Cliffhanger bait

- I found something crazy
- You won't believe what
- I have a secret
- Something interesting about your business
- Something surprising
- I noticed a weird thing
- Curious about something I found

## Sales language

- Hop on a quick call
- Jump on a call
- Get on a call
- Book a call
- Free strategy session
- Complimentary audit
- No obligation
- Discounted rate
- Limited time
- Special offer

## Filler / weak openers

- Just checking in
- Following up
- Circling back
- Bumping this
- Wanted to touch base
- Touch base
- Quick question

## Grammatical AI tells

- Delve into
- In the realm of
- Tapestry
- Symphony
- Testament to
- Meticulously
- It's worth noting

## Punctuation

- ` — ` (em-dash with spaces — surrounding rule is drafts shouldn't use em-dashes)
- Triple exclamation marks (`!!!`)

---

Update this file as new AI-flavored phrases surface in HITL rejections. Log additions with a date + example draft in the git commit message.
