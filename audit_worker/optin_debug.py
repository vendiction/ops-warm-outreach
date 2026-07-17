"""Diagnose + perform an opt-in against a REAL funnel page. Verbose on purpose:
prints exactly what inputs/buttons exist, what it filled, what it clicked, and whether
the page actually changed (i.e. did the submit really go through).

    OPTIN_URL=... AUDIT_EMAIL=... python optin_debug.py
"""
import asyncio
import os
import sys

URL = os.getenv("OPTIN_URL", "")
EMAIL = os.getenv("AUDIT_EMAIL", "")

EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name*="email" i]',
    'input[id*="email" i]',
    'input[placeholder*="email" i]',
]


async def run():
    from patchright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(30000)

        print(f"→ Loading {URL}")
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(3000)  # let JS render the form
        print(f"  title: {await page.title()}")

        # --- inventory the page (including iframes: MailerLite often embeds) ---
        frames = page.frames
        print(f"\n→ Frames on page: {len(frames)}")
        target = None
        for i, fr in enumerate(frames):
            try:
                n_inputs = await fr.locator("input").count()
                n_email = 0
                for sel in EMAIL_SELECTORS:
                    n_email += await fr.locator(sel).count()
                n_btn = await fr.locator("button, input[type=submit]").count()
                print(f"  [frame {i}] url={fr.url[:60]!r} inputs={n_inputs} email_inputs={n_email} buttons={n_btn}")
                if n_email and target is None:
                    target = fr
            except Exception as e:
                print(f"  [frame {i}] error: {e}")

        if target is None:
            print("\n✗ No email input found in ANY frame. Dumping all inputs on main frame:")
            for i in range(await page.locator("input").count()):
                el = page.locator("input").nth(i)
                print(f"   input[{i}] type={await el.get_attribute('type')!r} "
                      f"name={await el.get_attribute('name')!r} id={await el.get_attribute('id')!r} "
                      f"placeholder={await el.get_attribute('placeholder')!r} visible={await el.is_visible()}")
            await browser.close()
            return

        print(f"\n→ Using frame: {target.url[:70]!r}")

        # --- list buttons so we can see what the submit actually says ---
        print("\n→ Buttons in that frame:")
        btns = target.locator("button, input[type=submit]")
        for i in range(await btns.count()):
            b = btns.nth(i)
            try:
                txt = (await b.inner_text()) or (await b.get_attribute("value")) or ""
                print(f"   button[{i}] text={txt.strip()[:40]!r} type={await b.get_attribute('type')!r} "
                      f"visible={await b.is_visible()}")
            except Exception:
                pass

        # --- fill the email ---
        filled = False
        for sel in EMAIL_SELECTORS:
            el = target.locator(sel).first
            if await el.count() and await el.is_visible():
                await el.click()
                await el.fill(EMAIL)
                val = await el.input_value()
                print(f"\n✓ Filled {sel} -> {val!r}")
                filled = bool(val)
                break
        if not filled:
            print("\n✗ Could not fill an email field.")
            await browser.close()
            return

        # --- submit: prefer a real submit button, else press Enter ---
        submitted = False
        submit_btn = target.locator('button[type="submit"], input[type="submit"]').first
        if await submit_btn.count() and await submit_btn.is_visible():
            txt = (await submit_btn.inner_text()) or "(no text)"
            print(f"→ Clicking submit button: {txt.strip()[:40]!r}")
            await submit_btn.click()
            submitted = True
        else:
            # any visible button whose text looks like a signup CTA
            for i in range(await btns.count()):
                b = btns.nth(i)
                try:
                    t = ((await b.inner_text()) or "").lower()
                    if await b.is_visible() and any(w in t for w in
                            ["subscribe", "sign up", "join", "get", "send", "submit", "download", "yes", "claim"]):
                        print(f"→ Clicking button by text: {t.strip()[:40]!r}")
                        await b.click()
                        submitted = True
                        break
                except Exception:
                    continue
        if not submitted:
            print("→ No submit button matched; pressing Enter in the field instead")
            await target.locator(EMAIL_SELECTORS[0]).first.press("Enter")

        # --- verify something actually happened ---
        await page.wait_for_timeout(6000)
        body = (await page.locator("body").inner_text()).lower()
        success_words = ["thank", "success", "check your", "confirm", "almost", "you're in", "youre in", "subscribed"]
        hit = [w for w in success_words if w in body]
        print(f"\n→ Post-submit URL: {page.url[:80]}")
        if hit:
            print(f"✓ SUCCESS — page shows confirmation text: {hit}")
        else:
            print("? No obvious confirmation text. First 300 chars of page:")
            print("  " + body[:300].replace("\n", " "))
            await page.screenshot(path="optin_result.png")
            print("  (screenshot saved to optin_result.png)")

        await browser.close()


if __name__ == "__main__":
    if not URL or not EMAIL:
        sys.exit("Set OPTIN_URL and AUDIT_EMAIL")
    asyncio.run(run())
