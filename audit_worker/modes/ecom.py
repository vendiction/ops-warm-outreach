"""Ecom cart-abandon audit. Land on the product/funnel page, add to cart, begin
checkout, enter the disposable email, then abandon (never complete the order)."""
from modes.base import BaseMode


class EcomAbandonMode(BaseMode):
    async def _flow(self, page) -> None:
        await self._goto(page, self.funnel_url)

        # Add to cart (best-effort across common themes).
        await self._click_text(page, ["add to cart", "add to bag", "buy", "add"])
        await page.wait_for_timeout(1500)

        # Head to checkout. Try common paths, then a checkout button.
        base = "/".join(self.funnel_url.split("/")[:3])
        for path in ("/checkout", "/cart"):
            try:
                await self._goto(page, base + path)
                if await page.locator("form").count():
                    break
            except Exception:
                continue
        await self._click_text(page, ["checkout", "check out", "continue to checkout"])
        await page.wait_for_timeout(1500)

        # Enter email to trigger the abandoned-cart capture, then STOP (abandon).
        filled = await self._fill_first_email(page)
        if filled:
            # Some checkouts capture on blur/continue; nudge without completing payment.
            await self._click_text(page, ["continue", "next", "continue to shipping"])
        await page.wait_for_timeout(1500)
        # Intentionally do not submit payment. Leaving now = abandoned cart.
