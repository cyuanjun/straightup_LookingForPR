"""Smoke-fire the daily evening check-in (symptom_diary_due) on demand.

Sends the "Auntie Lim, 今天身体怎么样?" check-in to the linked parent's DM
right now, regardless of the configured 20:00 cron. Useful for rehearsing the
parent voice-diary flow without waiting until evening.

Usage:
    python scripts/fire_checkin.py

Requires:
  - .env populated, parent handshake done (families.parent_user_id set,
    users.telegram_chat_id set on the parent row)
  - Main app should NOT be running concurrently — both processes would compete
    for the same scheduler jobstore.

The script does not insert any event itself. The check-in only logs a
`parent_reply_transcribed` (and possibly `symptom_entry`) event WHEN the parent
replies, via the live voice/text handler. Run the main app afterwards to test
the full reply loop.
"""

from __future__ import annotations

import asyncio
import sys

from app.bot.app import build_application
from app.config import settings
from app.db import families as families_repo
from app.scheduler.jobs import symptom_diary_due


async def main() -> None:
    family_id = settings.demo_family_id
    if not family_id:
        print("ERROR: DEMO_FAMILY_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    state = await families_repo.state(family_id)
    if state != "active":
        missing = await families_repo.missing_fields(family_id)
        print(
            f"ERROR: family state = {state}; missing fields: {missing}",
            file=sys.stderr,
        )
        sys.exit(1)

    app = build_application()
    await app.initialize()
    await app.start()

    print("Firing symptom_diary_due — check-in goes to parent DM now…")
    await symptom_diary_due(family_id)

    # Tiny grace window so any TTS / send_voice fully flushes before teardown
    await asyncio.sleep(2)

    await app.stop()
    await app.shutdown()
    print("done — reply on the parent's Telegram to test the diary loop.")


if __name__ == "__main__":
    asyncio.run(main())
