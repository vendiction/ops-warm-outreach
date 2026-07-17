"""Info application / book-a-call audit. Start the application or booking flow,
submit the disposable email, then exit before completing (abandoned application)."""
from modes.base import BaseMode


class InfoApplicationMode(BaseMode):
    async def _flow(self, page) -> None:
        await self._goto(page, self.funnel_url)
        await page.wait_for_timeout(1000)

        # Enter the application/booking flow if it's behind a CTA.
        await self._click_text(page, ["apply", "book", "schedule", "get started", "start", "book a call"])
        await page.wait_for_timeout(1500)

        filled = await self._fill_first_email(page)
        if filled:
            # Provide email + advance one step to trigger the follow-up sequence,
            # then STOP — do not finish the application/booking.
            await self._click_text(page, ["next", "continue", "submit"])
            await page.wait_for_timeout(1500)
