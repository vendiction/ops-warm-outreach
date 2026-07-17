"""Info opt-in / lead-magnet audit. Land on the opt-in page, submit the disposable
email to enter the nurture sequence, then exit."""
from modes.base import BaseMode


class InfoOptinMode(BaseMode):
    async def _flow(self, page) -> None:
        await self._goto(page, self.funnel_url)
        await page.wait_for_timeout(1000)

        filled = await self._fill_first_email(page)
        if not filled:
            # Some pages gate the form behind a CTA ("Get the free guide") first.
            await self._click_text(page, ["get", "download", "free", "access", "join"])
            await page.wait_for_timeout(1000)
            filled = await self._fill_first_email(page)

        if filled:
            await self._submit(page)
            await page.wait_for_timeout(2000)  # let any double-optin/confirmation fire
