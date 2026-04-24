"""Spine smoke test — fires the caregiver loop without waiting for wall-clock 8:45.

Usage:
  python scripts/fire_demo.py                 # happy-path (parent confirms before window close)
  python scripts/fire_demo.py --fast          # use DEMO_MODE_FAST_FORWARD (windows ~30s)
  python scripts/fire_demo.py --missed        # parent never confirms → full escalation path
  python scripts/fire_demo.py --fast --missed # both

Requires:
  - Supabase schema + seed run
  - .env filled in
  - Family is "active": parent_user_id + primary_caregiver_user_id + group_chat_id all set
    (so patch users.telegram_user_id, users.telegram_chat_id, and families.group_chat_id
     manually in Supabase if you're not doing a real handshake/linkfamily flow)
  - PTB Application built (this script builds it but does NOT start a webhook —
    so sends are one-way; callbacks from ✓ Sent are handled when the real bot process is running)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.bot.app import build_application
from app.config import settings
from app.db import families as families_repo
from app.db import medications as medications_repo
from app.scheduler.jobs import med_reminder_due


async def main(fast: bool, missed: bool) -> None:
    if fast:
        os.environ["DEMO_MODE_FAST_FORWARD"] = "true"
        settings.demo_mode_fast_forward = True

    family_id = settings.demo_family_id
    if not family_id:
        print("ERROR: DEMO_FAMILY_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    # Precondition check
    state = await families_repo.state(family_id)
    if state != "active":
        missing = await families_repo.missing_fields(family_id)
        print(
            f"ERROR: family state = {state}; missing fields: {missing}\n"
            "See scripts/fire_demo.py docstring for how to patch users + group_chat_id.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Need PTB app initialized to send messages
    app = build_application()
    await app.initialize()
    await app.start()

    meds = await medications_repo.list_active(family_id)
    if not meds:
        print("ERROR: no active medications for demo family", file=sys.stderr)
        sys.exit(1)
    med = meds[0]
    print(f"Firing med_reminder_due for {med['name']} {med['dose']}…")

    # Need the scheduler running so confirmation_window_close gets scheduled
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    scheduler.start()

    await med_reminder_due(family_id, med["id"])

    if missed:
        # Simulate: parent never confirms → let the window-close job fire naturally.
        # Wait long enough for the window to elapse + the check-back to fire.
        window_s = 60 if fast else settings.confirmation_window_min * 60
        checkback_s = 60 if fast else settings.check_back_offset_min * 60
        total = window_s + checkback_s + 10
        print(f"--missed: sleeping {total}s to let window-close + check-back fire…")
        await asyncio.sleep(total)
    else:
        # Happy path: simulate a confirm_med event directly (no voice input)
        from datetime import datetime
        from app.db import events as events_repo
        from app.bot.group_post import post_resolution

        await asyncio.sleep(2)  # let the reminder log settle
        await events_repo.insert(
            family_id,
            "med_confirmed",
            payload={
                "medication_id": med["id"],
                "transcript": "(simulated confirm via fire_demo --happy)",
                "confidence": 1.0,
                "source": "caregiver_sent",
            },
            medication_id=med["id"],
        )
        await post_resolution(app.bot, family_id, med, datetime.now())
        await asyncio.sleep(2)

    # Print digest output for verification
    from app.bot.digest import compute as compute_digest

    text = await compute_digest(family_id)
    print("\n--- /digest ---")
    print(text)
    print("---------------\n")

    # Teardown
    scheduler.shutdown(wait=False)
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fast", action="store_true", help="Fast-forward reminder windows (~30s)")
    p.add_argument(
        "--missed", action="store_true", help="Simulate missed confirmation → full escalation"
    )
    args = p.parse_args()
    asyncio.run(main(fast=args.fast, missed=args.missed))
