"""Read + write admin dashboard — /admin/<family_id>.

Web UI for all caregiver-facing admin tasks:
  - Medications: add / edit times / delete (scheduler auto-syncs)
  - Rotation: assign caregivers per day
  - Caregivers: add / delete (no Telegram link required at creation time)
  - Family settings: primary caregiver, pause/resume, languages, symptom-diary time
  - Parent handshake + group linking: generate tokens / codes on-demand

Telegram is reserved for parent ↔ agent interactions, ✓ Sent taps, /help, /stop.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import medications as medications_repo
from app.db import rotation as rotation_repo
from app.db import tokens as tokens_repo
from app.db import users as users_repo
from app.scheduler.jobs import register_all_family_crons

router = APIRouter(prefix="/admin")

DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# All user-facing timestamps render in the family's configured TZ (default Asia/Singapore).
LOCAL_TZ = ZoneInfo(settings.tz)


def _tz_label() -> str:
    """Render LOCAL_TZ's current UTC offset as e.g. 'GMT +8' or 'GMT -5:30'."""
    offset = datetime.now(LOCAL_TZ).utcoffset()
    if offset is None:
        return ""
    total_min = int(offset.total_seconds() / 60)
    hours, mins = divmod(abs(total_min), 60)
    sign = "+" if total_min >= 0 else "-"
    if mins == 0:
        return f"GMT {sign}{hours}"
    return f"GMT {sign}{hours}:{mins:02d}"


# ---------------------------------------------------------------------------
# Shortcut: landing page
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def root_redirect():
    if not settings.demo_family_id:
        raise HTTPException(404, "Set DEMO_FAMILY_ID in .env to use /admin without a family id")
    return RedirectResponse(f"/admin/{settings.demo_family_id}")


# ---------------------------------------------------------------------------
# GET /admin/{family_id} — dashboard
# ---------------------------------------------------------------------------


@router.get("/{family_id}", response_class=HTMLResponse)
async def family_dashboard(family_id: str) -> HTMLResponse:
    family = await families_repo.get(family_id)
    if not family:
        raise HTTPException(404, f"Family {family_id} not found")

    all_users = await users_repo.list_all(family_id)
    meds = await medications_repo.list_active(family_id)
    rotation = await rotation_repo.list_for_family(family_id)
    state = await families_repo.state(family_id)
    missing = await families_repo.missing_fields(family_id) if state == "inactive_missing_fields" else []

    from app.scheduler.scheduler import get_scheduler

    try:
        all_jobs = get_scheduler().get_jobs()
    except Exception:
        all_jobs = []
    family_jobs = [j for j in all_jobs if (j.args or [None])[0] == family_id]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    raw_events = await events_repo.recent_for_briefing(family_id, window_days=1)
    events = sorted(
        [
            e
            for e in raw_events
            if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) >= cutoff
        ],
        key=lambda e: e["created_at"],
        reverse=True,
    )

    user_by_id = {u["id"]: u for u in all_users}
    parent = user_by_id.get(family.get("parent_user_id"))
    primary = user_by_id.get(family.get("primary_caregiver_user_id"))
    today_dow = (datetime.now().weekday() + 1) % 7
    on_duty_today_id = await rotation_repo.on_duty(family_id, today_dow)
    on_duty_today = user_by_id.get(on_duty_today_id) if on_duty_today_id else None

    status = _compute_status(state, missing, events, family_jobs)

    html = _render_home(
        family=family,
        state=state,
        missing=missing,
        status=status,
        parent=parent,
        primary=primary,
        all_users=all_users,
        user_by_id=user_by_id,
        meds=meds,
        rotation=rotation,
        today_dow=today_dow,
        on_duty_today=on_duty_today,
        family_jobs=family_jobs,
        events=events,
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# GET /admin/{family_id}/settings — settings page (caregivers + config + onboarding)
# ---------------------------------------------------------------------------


@router.get("/{family_id}/medications", response_class=HTMLResponse)
async def medications_page(family_id: str) -> HTMLResponse:
    family = await families_repo.get(family_id)
    if not family:
        raise HTTPException(404, f"Family {family_id} not found")

    meds = await medications_repo.list_active(family_id)
    state = await families_repo.state(family_id)
    missing = await families_repo.missing_fields(family_id) if state == "inactive_missing_fields" else []

    html = _render_medications(family=family, state=state, missing=missing, meds=meds)
    return HTMLResponse(html)


@router.get("/{family_id}/settings", response_class=HTMLResponse)
async def settings_page(family_id: str, saved: str | None = None) -> HTMLResponse:
    family = await families_repo.get(family_id)
    if not family:
        raise HTTPException(404, f"Family {family_id} not found")

    all_users = await users_repo.list_all(family_id)
    rotation = await rotation_repo.list_for_family(family_id)
    state = await families_repo.state(family_id)
    missing = await families_repo.missing_fields(family_id) if state == "inactive_missing_fields" else []
    user_by_id = {u["id"]: u for u in all_users}
    today_dow = (datetime.now().weekday() + 1) % 7

    html = _render_settings(
        family=family,
        state=state,
        missing=missing,
        all_users=all_users,
        rotation=rotation,
        user_by_id=user_by_id,
        today_dow=today_dow,
        saved=saved == "1",
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# POST routes — form actions (all redirect back to the appropriate page)
# ---------------------------------------------------------------------------


def _back_to(family_id: str, anchor: str = "", page: str = "home") -> RedirectResponse:
    url = f"/admin/{family_id}"
    if page == "settings":
        url += "/settings"
    elif page == "medications":
        url += "/medications"
    if anchor:
        url += f"#{anchor}"
    return RedirectResponse(url, status_code=303)


def _parse_times(raw: str) -> list[str]:
    """Parse '08:45, 20:00' → ['08:45', '20:00'] with basic validation."""
    out: list[str] = []
    for tok in (raw or "").replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        # Accept HH:MM or HH:MM:SS
        parts = tok.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(f"Bad time: {tok!r}")
        hh = int(parts[0])
        mm = int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"Bad time: {tok!r}")
        out.append(f"{hh:02d}:{mm:02d}")
    if not out:
        raise ValueError("At least one time required")
    return sorted(set(out))


# --- Medications -----------------------------------------------------------


@router.post("/{family_id}/medications")
async def add_medication(
    family_id: str,
    name: str = Form(...),
    dose: str = Form(...),
    times: str = Form(...),
):
    try:
        parsed_times = _parse_times(times)
    except ValueError as e:
        raise HTTPException(400, str(e))
    med = await medications_repo.create(family_id, name.strip(), dose.strip(), parsed_times)
    await _sync_scheduler_for(med["id"])
    return _back_to(family_id, page="medications")


@router.post("/{family_id}/medications/{med_id}/update")
async def update_medication(
    family_id: str,
    med_id: str,
    name: str = Form(...),
    dose: str = Form(...),
    times: str = Form(...),
):
    try:
        parsed_times = _parse_times(times)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await medications_repo.update(med_id, name=name.strip(), dose=dose.strip(), times=parsed_times)
    await _sync_scheduler_for(med_id)
    return _back_to(family_id, page="medications")


@router.post("/{family_id}/medications/{med_id}/delete")
async def delete_medication(family_id: str, med_id: str):
    await medications_repo.deactivate(med_id)  # soft-delete via active=false
    await _sync_scheduler_for(med_id)
    return _back_to(family_id, page="medications")


async def _sync_scheduler_for(med_id: str) -> None:
    """Remove stale cron jobs + re-register from the medication's current times."""
    try:
        from app.scheduler.jobs import sync_jobs_for_medication

        await sync_jobs_for_medication(med_id)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("sync_jobs_for_medication failed for %s", med_id)


# --- Caregivers ------------------------------------------------------------


@router.post("/{family_id}/users")
async def add_caregiver(family_id: str, display_name: str = Form(...)):
    await users_repo.create_unlinked_caregiver(family_id, display_name.strip())
    return _back_to(family_id, "users", page="settings")


@router.post("/{family_id}/users/{user_id}/delete")
async def delete_user(family_id: str, user_id: str):
    from app.db.client import get_client

    client = await get_client()
    await client.table("users").delete().eq("id", user_id).eq("family_id", family_id).execute()
    return _back_to(family_id, "users", page="settings")


@router.post("/{family_id}/users/{user_id}/set-primary")
async def set_primary(family_id: str, user_id: str):
    await families_repo.set_primary_caregiver(family_id, user_id)
    return _back_to(family_id, page="settings")


# --- Rotation --------------------------------------------------------------


@router.post("/{family_id}/rotation")
async def set_rotation(family_id: str, day_0: str = Form(""), day_1: str = Form(""), day_2: str = Form(""), day_3: str = Form(""), day_4: str = Form(""), day_5: str = Form(""), day_6: str = Form("")):
    values = [day_0, day_1, day_2, day_3, day_4, day_5, day_6]
    for dow, user_id in enumerate(values):
        if user_id:
            await rotation_repo.assign(family_id, dow, user_id)
        else:
            # blank = unassign → delete the row
            from app.db.client import get_client

            client = await get_client()
            await client.table("rotation").delete().eq("family_id", family_id).eq(
                "day_of_week", dow
            ).execute()
    return _back_to(family_id, "rotation", page="settings")


# --- Family settings -------------------------------------------------------


@router.post("/{family_id}/settings")
async def update_settings(
    family_id: str,
    languages: str = Form(""),
    timezone_name: str = Form(""),
    daily_report_time: str = Form(""),
    symptom_diary_time: str = Form(""),
):
    from app.db.client import get_client

    patch: dict = {}
    if languages:
        patch["languages"] = languages.strip()
    if timezone_name:
        patch["timezone"] = timezone_name.strip()
    for key, raw in (
        ("daily_report_time", daily_report_time),
        ("symptom_diary_time", symptom_diary_time),
    ):
        if raw:
            parts = raw.split(":")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                patch[key] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    if patch:
        client = await get_client()
        await client.table("families").update(patch).eq("id", family_id).execute()
        # Re-register family crons so the new times take effect immediately
        try:
            await register_all_family_crons()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Failed to re-register family crons")
    return RedirectResponse(f"/admin/{family_id}/settings?saved=1#settings", status_code=303)


@router.post("/{family_id}/pause")
async def toggle_pause(family_id: str):
    fam = await families_repo.get(family_id)
    await families_repo.set_paused(family_id, not (fam or {}).get("paused", False))
    return _back_to(family_id, page="settings")


@router.post("/{family_id}/set-group-chat")
async def set_group_chat(family_id: str, group_chat_id: str = Form(...)):
    try:
        gid = int(group_chat_id.strip())
    except ValueError:
        raise HTTPException(400, "group_chat_id must be an integer (usually negative)")
    await families_repo.set_group_chat_id(family_id, gid)
    return _back_to(family_id, "settings", page="settings")


# --- Handshake / group-link tokens ----------------------------------------


@router.post("/{family_id}/generate-handshake")
async def generate_handshake(family_id: str, caregiver_user_id: str = Form(...)):
    """Generate a parent-handshake token + a group-linking setup code, both 24h."""
    token = await tokens_repo.create_parent_handshake(family_id, caregiver_user_id)
    _, setup_code = await tokens_repo.create_group_linking(family_id, caregiver_user_id)
    # Redirect to settings page with tokens visible in query params
    return RedirectResponse(
        f"/admin/{family_id}/settings?generated_token={token}&generated_code={setup_code}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# State-machine inference for the hero banner
# ---------------------------------------------------------------------------


def _compute_status(
    fam_state: str, missing: list[str], events: list[dict], jobs: list
) -> dict:
    now = datetime.now(timezone.utc)

    if fam_state == "inactive_missing_fields":
        return {
            "icon": "⚠️",
            "title": "Setup incomplete",
            "detail": f"Missing: {', '.join(missing)} — reminders will not fire until this is resolved",
            "accent": "#a83232",
        }
    if fam_state == "paused":
        return {
            "icon": "⏸",
            "title": "Paused",
            "detail": "Reminders are paused. Click Resume in the Settings section to re-enable.",
            "accent": "#c27d00",
        }

    if events:
        latest = events[0]
        t = latest["type"]
        age_s = (now - datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))).total_seconds()
        age_str = _fmt_delta(age_s)

        if t == "med_reminder_sent" and age_s < 20 * 60:
            return {"icon": "🔔", "title": "Reminder sent — awaiting parent confirmation",
                    "detail": f"Sent {age_str} ago. Window closes when the confirmation_window_close job fires.",
                    "accent": "#2d5ea8"}
        if t == "escalation_posted" and age_s < 20 * 60:
            return {"icon": "⚠️", "title": "Missed — escalation posted to family group",
                    "detail": f"Posted {age_str} ago. Awaiting caregiver ✓ Sent tap.", "accent": "#c27d00"}
        if t == "nudge_sent_by_caregiver" and age_s < 20 * 60:
            return {"icon": "✍️", "title": "Caregiver sent the nudge",
                    "detail": f"{age_str} ago. Aunty May's check-back is scheduled next.", "accent": "#2d5ea8"}
        if t == "check_back_sent" and age_s < 20 * 60:
            return {"icon": "🔔", "title": "Check-back sent — awaiting parent reply",
                    "detail": f"{age_str} ago. Parent reply will close this cycle.", "accent": "#2d5ea8"}
        if t == "med_confirmed" and age_s < 2 * 60 * 60:
            timing = (latest.get("payload") or {}).get("timing", "?")
            slot = (latest.get("payload") or {}).get("slot", "?")
            return {"icon": "✅", "title": f"Confirmed ({timing}) for slot {slot}",
                    "detail": f"{age_str} ago. Cycle closed.", "accent": "#2d7a2d"}
        if t == "urgent_symptom_escalated" and age_s < 60 * 60:
            return {"icon": "🚨", "title": "Urgent symptom — all caregivers DM'd",
                    "detail": f"{age_str} ago. Parent received 995 safety script.", "accent": "#a83232"}

    upcoming = [j for j in jobs if j.next_run_time]
    if upcoming:
        next_job = min(upcoming, key=lambda j: j.next_run_time)
        when_local = next_job.next_run_time.astimezone(LOCAL_TZ).strftime("%a %d %b · %H:%M")
        label = _job_label(next_job.id).lower()
        return {"icon": "⏳", "title": f"Next: {label} — {when_local} {_tz_label()}",
                "detail": f"job <code>{escape(next_job.id)}</code>",
                "accent": "#555c6e"}

    return {"icon": "💤", "title": "Idle — no scheduled reminders",
            "detail": "Add a medication below to start the cycle.", "accent": "#6a6a6a"}


def _job_label(job_id: str) -> str:
    """Human label for the hero banner + grouped scheduled-jobs section."""
    if job_id.startswith("med_reminder:"):
        return "Medication reminder"
    if job_id.startswith("daily_report:"):
        return "Daily report"
    if job_id.startswith("symptom_diary:"):
        return "Daily check-in"
    if job_id.startswith("weekly_digest:"):
        return "Weekly digest"
    if job_id.startswith("check_back:"):
        return "Aunty May check-back"
    if job_id.startswith("win_close:") or job_id.startswith("confirmation_window_close:"):
        return "Confirmation window close"
    if job_id.startswith("appointment_reminder:"):
        return "Appointment reminder"
    return "Other"


# Preferred display order for grouped scheduled-jobs table
_JOB_GROUP_ORDER = [
    "Medication reminder",
    "Daily report",
    "Daily check-in",
    "Weekly digest",
    "Appointment reminder",
    "Aunty May check-back",
    "Confirmation window close",
    "Other",
]


def _fmt_delta(seconds: float) -> str:
    seconds = int(seconds)
    neg = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {s}s{' ago' if neg else ''}"
    hours, m = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {m}m{' ago' if neg else ''}"
    days, h = divmod(hours, 24)
    return f"{days}d {h}h{' ago' if neg else ''}"


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def _state_chip(state: str, missing: list[str]) -> str:
    colors = {"active": "#2d7a2d", "paused": "#c27d00",
              "inactive_missing_fields": "#a83232", "not_found": "#6a6a6a"}
    label = state
    if state == "inactive_missing_fields":
        label = f"inactive (missing: {', '.join(missing)})"
    return (f'<span style="background:{colors.get(state, "#555")};padding:4px 10px;'
            f'border-radius:12px;font-size:12px;color:white;font-weight:600;">{escape(label)}</span>')


def _user_card(u: dict | None, label: str) -> str:
    if u is None:
        return (f'<div class="card muted"><div class="label">{escape(label)}</div>'
                f'<div class="value">— not set —</div></div>')
    linked = "🔗" if u.get("telegram_user_id") else "⏳"
    tg = u.get("telegram_user_id") or "unlinked"
    return (f'<div class="card"><div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(u["display_name"])}</div>'
            f'<div class="sub">{linked} {escape(str(tg))} · {escape(u["role"])}</div></div>')


def _status_hero(status: dict) -> str:
    return (f'<div class="hero" style="border-left: 4px solid {status["accent"]};">'
            f'<div class="hero-icon">{status["icon"]}</div>'
            f'<div><div class="hero-title">{escape(status["title"])}</div>'
            f'<div class="hero-detail">{status["detail"]}</div></div></div>')


def _job_recurrence(job) -> str:
    """Return 'Daily' / 'Weekly' / 'One-shot' / 'Other' by inspecting the trigger."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger

    trigger = job.trigger
    if isinstance(trigger, DateTrigger):
        return "One-shot"
    if isinstance(trigger, CronTrigger):
        for field in trigger.fields:
            if field.name == "day_of_week" and str(field) != "*":
                return "Weekly"
        return "Daily"
    return "Other"


def _jobs_table(jobs: list) -> str:
    if not jobs:
        return '<p class="muted">No scheduled jobs for this family.</p>'
    now = datetime.now(timezone.utc)

    FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)
    ordered = sorted(jobs, key=lambda j: j.next_run_time or FAR_FUTURE)

    rows = []
    for i, j in enumerate(ordered, start=1):
        if j.next_run_time:
            nr_local = j.next_run_time.astimezone(LOCAL_TZ).strftime("%a %d %b · %H:%M")
            countdown = _fmt_delta((j.next_run_time - now).total_seconds())
            nr = (
                f"{escape(nr_local)} {escape(_tz_label())} "
                f"<span class='muted'>({escape(countdown)})</span>"
            )
        else:
            nr = "—"
        rows.append(
            f"<tr>"
            f"<td class='muted nowrap'>#{i}</td>"
            f"<td>{escape(_job_label(j.id))}</td>"
            f"<td><span class='badge-type'>{escape(_job_recurrence(j))}</span></td>"
            f"<td>{nr}</td>"
            f"</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th style='width:40px'>#</th>"
        "<th>Name</th>"
        "<th>Type</th>"
        "<th>Next run</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _time_options(selected: str = "", include_blank: bool = True) -> str:
    """Generate <option> tags for 15-min intervals across 24h."""
    opts = ['<option value="">—</option>'] if include_blank else []
    for h in range(24):
        for m in (0, 15, 30, 45):
            t = f"{h:02d}:{m:02d}"
            sel = " selected" if t == selected else ""
            opts.append(f'<option value="{t}"{sel}>{t}</option>')
    return "".join(opts)


def _time_row_html(selected: str = "") -> str:
    return (
        '<div class="time-row">'
        f'<select class="time-select">{_time_options(selected)}</select>'
        '<button type="button" class="btn-icon" onclick="removeTime(this)" title="Remove">×</button>'
        '</div>'
    )


def _med_dialog(
    dialog_id: str,
    title: str,
    form_action: str,
    name: str = "",
    dose: str = "",
    times: list[str] | None = None,
) -> str:
    """Render a <dialog> with the add/edit form inside."""
    tlist = times or []
    if tlist:
        time_rows = "".join(_time_row_html(t) for t in tlist)
    else:
        time_rows = _time_row_html()
    return f"""
    <dialog id="{escape(dialog_id)}" class="med-dialog">
      <form method="post" action="{escape(form_action)}" onsubmit="return syncTimes(this)">
        <h3>{escape(title)}</h3>
        <label>Name<input name="name" value="{escape(name)}" placeholder="Lisinopril" required autocomplete="off" /></label>
        <label>Dose<input name="dose" value="{escape(dose)}" placeholder="10mg" required autocomplete="off" /></label>
        <label>Times
          <div class="time-rows">{time_rows}</div>
          <button type="button" class="btn-small" onclick="addTime(this)">+ Add time</button>
        </label>
        <input type="hidden" name="times" />
        <div class="dialog-actions">
          <button type="button" onclick="this.closest('dialog').close()">Cancel</button>
          <button type="submit" class="primary">Save</button>
        </div>
      </form>
    </dialog>"""


_MED_DIALOG_JS = """
<script>
  function addTime(btn) {
    const rows = btn.previousElementSibling;
    const first = rows.firstElementChild.cloneNode(true);
    first.querySelector('select').value = '';
    rows.appendChild(first);
  }
  function removeTime(btn) {
    const row = btn.parentElement;
    const container = row.parentElement;
    if (container.children.length > 1) row.remove();
    else btn.closest('.time-row').querySelector('select').value = '';
  }
  function syncTimes(form) {
    const selects = form.querySelectorAll('.time-select');
    const values = [...selects].map(s => s.value).filter(v => v);
    if (values.length === 0) { alert('Add at least one time.'); return false; }
    form.querySelector('input[name="times"]').value = values.join(',');
    return true;
  }
</script>"""


def _meds_section(family_id: str, meds: list[dict]) -> str:
    """Table view of medications + top-right [+ Add] button that opens a modal."""
    # Rows
    rows: list[str] = []
    edit_dialogs: list[str] = []
    for m in meds:
        mid = m["id"]
        times_list = [str(t)[:5] for t in (m.get("times") or [])]
        times_str = ", ".join(times_list) or "—"
        rows.append(f"""
          <tr>
            <td><b>{escape(m['name'])}</b></td>
            <td>{escape(m.get('dose', ''))}</td>
            <td class="nowrap">{escape(times_str)}</td>
            <td class="meds-actions">
              <button type="button" onclick="document.getElementById('dialog-edit-{escape(mid)}').showModal()">Edit</button>
              <form method="post"
                    action="/admin/{escape(family_id)}/medications/{escape(mid)}/delete"
                    onsubmit="return confirm('Delete {escape(m['name'])}?');"
                    style="display:inline">
                <button type="submit" class="danger">Delete</button>
              </form>
            </td>
          </tr>""")
        edit_dialogs.append(
            _med_dialog(
                dialog_id=f"dialog-edit-{mid}",
                title="Edit medication",
                form_action=f"/admin/{family_id}/medications/{mid}/update",
                name=m["name"],
                dose=m.get("dose", ""),
                times=times_list,
            )
        )

    body = (
        "".join(rows)
        if meds
        else '<tr><td colspan="4" class="muted" style="text-align:center;padding:28px;font-style:italic">No medications yet. Click <b>+ Add medication</b> to create one.</td></tr>'
    )

    add_dialog = _med_dialog(
        dialog_id="dialog-add",
        title="Add medication",
        form_action=f"/admin/{family_id}/medications",
    )

    return f"""
    <div class="section-head">
      <button type="button" class="primary btn-add" onclick="document.getElementById('dialog-add').showModal()">+ Add medication</button>
    </div>
    <table class="meds-table">
      <thead>
        <tr><th style="width:30%">Name</th><th style="width:15%">Dose</th><th>Times</th><th style="width:1%"></th></tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
    {add_dialog}
    {''.join(edit_dialogs)}
    {_MED_DIALOG_JS}"""


def _rotation_section(
    family_id: str, rotation: list[dict], user_by_id: dict, caregivers: list[dict], today_dow: int
) -> str:
    by_day = {r["day_of_week"]: r["user_id"] for r in rotation}
    options_base = '<option value="">— unassigned —</option>' + "".join(
        f'<option value="{escape(c["id"])}">{escape(c["display_name"])}</option>'
        for c in caregivers
    )
    rows = []
    for dow, label in enumerate(DAYS):
        current = by_day.get(dow, "")
        options = options_base.replace(
            f'value="{escape(current)}"', f'value="{escape(current)}" selected'
        ) if current else options_base.replace('value=""', 'value="" selected', 1)
        is_today = dow == today_dow
        day_cell = (
            f'<span style="color:#5ab55a;font-weight:700">{escape(label)} (TODAY)</span>'
            if is_today
            else escape(label)
        )
        tr_bg = ' style="background:#1a2a1a"' if is_today else ""
        rows.append(
            f'<tr{tr_bg}><td>{day_cell}</td><td><select name="day_{dow}">{options}</select></td></tr>'
        )
    return f"""
    <form method="post" action="/admin/{escape(family_id)}/rotation" id="rotation">
      <table><thead><tr><th>Day</th><th>On duty</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
      <div style="margin-top:10px;text-align:right"><button type="submit" class="primary">Save rotation</button></div>
    </form>"""


def _users_section(family_id: str, users: list[dict], primary_id: str | None) -> str:
    rows = []
    for u in users:
        linked = "🔗" if u.get("telegram_user_id") else "⏳"
        tg = u.get("telegram_user_id") or "unlinked"
        is_primary = u["id"] == primary_id
        primary_badge = ' <span class="badge">primary</span>' if is_primary else ""
        actions = ""
        if u["role"] == "caregiver":
            if not is_primary:
                actions += f"""
                  <form method="post" action="/admin/{escape(family_id)}/users/{escape(u['id'])}/set-primary" style="display:inline">
                    <button type="submit">Set primary</button>
                  </form>"""
            actions += f"""
              <form method="post" action="/admin/{escape(family_id)}/users/{escape(u['id'])}/delete"
                    onsubmit="return confirm('Delete {escape(u['display_name'])}?');" style="display:inline">
                <button type="submit" class="danger">Delete</button>
              </form>"""
        rows.append(f"""
          <tr>
            <td><b>{escape(u['display_name'])}</b>{primary_badge}</td>
            <td>{escape(u['role'])}</td>
            <td>{linked} <code>{escape(str(tg))}</code></td>
            <td>{escape(u.get('telegram_username') or '')}</td>
            <td>{actions}</td>
          </tr>""")
    return f"""
    <table id="users"><thead>
      <tr><th>Name</th><th>Role</th><th>Telegram</th><th>Username</th><th style="width:1%">Actions</th></tr>
    </thead><tbody>{''.join(rows)}</tbody></table>

    <form method="post" action="/admin/{escape(family_id)}/users" class="add-form">
      <b>Add caregiver</b>
      <input name="display_name" placeholder="Sibling's name" required />
      <button type="submit" class="primary">Add</button>
    </form>"""


def _settings_section(family_id: str, family: dict) -> str:
    pause_label = "Resume" if family.get("paused") else "Pause"
    dr = str(family.get("daily_report_time") or "")[:5]   # 'HH:MM'
    sd = str(family.get("symptom_diary_time") or "")[:5]
    return f"""
    <div id="settings" class="settings-grid">
      <form method="post" action="/admin/{escape(family_id)}/settings">
        <label>Languages <input name="languages" value="{escape(family.get('languages') or '')}" placeholder="zh+en" /></label>
        <label>Timezone <input name="timezone_name" value="{escape(family.get('timezone') or '')}" placeholder="Asia/Singapore" /></label>
        <label>Daily report time (group)
          <select name="daily_report_time">{_time_options(dr, include_blank=False)}</select>
        </label>
        <label>Daily check-in time (parent)
          <select name="symptom_diary_time">{_time_options(sd, include_blank=False)}</select>
        </label>
        <button type="submit" class="primary">Save settings</button>
      </form>

      <form method="post" action="/admin/{escape(family_id)}/set-group-chat">
        <label>Group chat ID <input name="group_chat_id" value="{escape(str(family.get('group_chat_id') or ''))}" placeholder="-100..." /></label>
        <button type="submit">Save group chat</button>
      </form>

      <form method="post" action="/admin/{escape(family_id)}/pause">
        <button type="submit" class="{'danger' if family.get('paused') else 'primary'}">{pause_label} reminders</button>
      </form>
    </div>"""


def _handshake_section(family_id: str, caregivers: list[dict]) -> str:
    if not caregivers:
        return '<p class="muted">Add a caregiver first.</p>'
    options = "".join(
        f'<option value="{escape(c["id"])}">{escape(c["display_name"])}</option>'
        for c in caregivers
    )
    return f"""
    <form method="post" action="/admin/{escape(family_id)}/generate-handshake" class="add-form">
      <b>Generate parent handshake + group-link code</b>
      <select name="caregiver_user_id">{options}</select>
      <button type="submit" class="primary">Generate</button>
      <span class="muted" style="font-size:12px">Both expire in 24h.</span>
    </form>"""


def _generated_banner(token: str | None, code: str | None) -> str:
    if not token and not code:
        return ""
    bot_username = settings.bot_username or "your_bot"
    parts = ['<div class="banner">', "<b>🎉 Generated — 24h TTL:</b><br/>"]
    if token:
        parts.append(
            f'<div>Parent deep link: <code>https://t.me/{escape(bot_username)}?start={escape(token)}</code></div>'
        )
    if code:
        parts.append(
            f'<div>Group linking: run <code>/linkfamily {escape(code)}</code> in the family Telegram group</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _events_timeline(events: list[dict], user_by_id: dict) -> str:
    if not events:
        return '<p class="muted">No events in the last 24h.</p>'
    rows = []
    for e in events:
        ts_local = (
            datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
            .astimezone(LOCAL_TZ)
            .strftime("%H:%M:%S")
        )
        type_ = e["type"]
        payload = e.get("payload") or {}
        actor_id = e.get("attributed_to")
        actor = user_by_id.get(actor_id, {}).get("display_name") if actor_id else ""
        summary = _event_summary(type_, payload)
        color = _event_type_color(type_)
        icon = _event_icon(type_)
        actor_html = f'<span class="muted">· {escape(actor)}</span>' if actor else ""
        rows.append(
            f'<div class="event-row"><div class="event-ts">{escape(ts_local)}</div>'
            f'<div class="event-icon" style="background:{color}">{icon}</div>'
            f'<div class="event-body"><div class="event-title">{escape(type_)} {actor_html}</div>'
            f'<div class="event-summary">{summary}</div></div></div>'
        )
    return f'<div class="events-list">{"".join(rows)}</div>'


def _event_summary(type_: str, payload: dict) -> str:
    if type_ == "med_confirmed":
        return escape(f"{payload.get('timing','')} · slot {payload.get('slot','?')} · source={payload.get('source','')}")
    if type_ == "med_reminder_sent":
        return escape(f"scheduled {payload.get('scheduled_time','')}")
    if type_ == "med_missed":
        return escape(f"window={payload.get('window_min','?')}min")
    if type_ == "escalation_posted":
        return escape(f"pattern={payload.get('pattern_count','?')} miss(es) · group_msg={payload.get('group_message_id','')}")
    if type_ == "nudge_sent_by_caregiver":
        return escape(f"reminder={str(payload.get('reminder_event_id',''))[:12]}")
    if type_ == "parent_reply_transcribed":
        t = payload.get("transcript", "")
        return f'<i>"{escape(t[:120])}"</i>' + (" …" if len(t) > 120 else "")
    if type_ == "urgent_symptom_escalated":
        return escape(f"symptom=\"{payload.get('symptom_text','?')}\" · dmed={len(payload.get('caregivers_dmed') or [])}")
    if type_ in ("clinical_question_deferred", "symptom_entry"):
        txt = payload.get("question_text") or payload.get("symptom_text", "")
        return f'<i>"{escape(txt[:100])}"</i>'
    if type_ == "partial_confirm":
        return escape(f"reason={payload.get('reason','?')}")
    parts = [f"<b>{escape(k)}</b>={escape(str(v)[:40])}" for k, v in payload.items()]
    return " · ".join(parts) or "—"


def _event_icon(type_: str) -> str:
    return {"med_reminder_sent": "🔔", "parent_reply_transcribed": "🎙", "med_confirmed": "✅",
            "partial_confirm": "⚠", "symptom_entry": "📝", "clinical_question_deferred": "🩺",
            "distress_escalated": "💔", "urgent_symptom_escalated": "🚨", "med_missed": "❌",
            "escalation_posted": "📣", "nudge_sent_by_caregiver": "✉", "check_back_sent": "🔁",
            "appointment_reminder_sent": "📅", "weekly_digest_sent": "📊",
            "briefing_generated": "📄", "parent_optout": "⏹"}.get(type_, "•")


def _event_type_color(type_: str) -> str:
    if type_ in ("urgent_symptom_escalated", "med_missed", "partial_confirm"):
        return "#a83232"
    if type_ in ("escalation_posted", "distress_escalated", "clinical_question_deferred"):
        return "#c27d00"
    if type_ in ("med_confirmed", "nudge_sent_by_caregiver", "check_back_sent"):
        return "#2d7a2d"
    if type_ in ("med_reminder_sent", "weekly_digest_sent", "symptom_entry", "parent_reply_transcribed"):
        return "#2d5ea8"
    return "#555"


_STYLES = """
  * { box-sizing: border-box; }
  body { font: 14px/1.55 -apple-system, system-ui, "Segoe UI", sans-serif; background: #0b0b10; color: #e4e4ea; margin: 0; padding: 24px; max-width: 1400px; margin-inline: auto; }
  h1 { font-size: 22px; margin: 0 0 4px; display: flex; align-items: center; gap: 12px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: #888; margin: 32px 0 12px; font-weight: 700; }
  .muted { color: #888; }
  code { font: 12px/1.3 "SF Mono", ui-monospace, monospace; color: #c4a3ff; background: #1a1a22; padding: 1px 5px; border-radius: 3px; }
  .nowrap { white-space: nowrap; }

  /* Navbar */
  .navbar { display: flex; align-items: center; gap: 20px; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid #24242d; }
  .navbar .brand { font-weight: 700; font-size: 15px; letter-spacing: 0.02em; color: #a4a4b4; }
  .navbar a { color: #9f9faf; text-decoration: none; font-weight: 600; font-size: 13px; padding: 6px 12px; border-radius: 6px; }
  .navbar a:hover { background: #1a1a22; color: #e4e4ea; }
  .navbar a.active { background: #2d5ea8; color: white; }

  .header-row { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
  .meta { font-size: 12px; color: #888; text-align: right; }
  .hero { background: linear-gradient(180deg, #1a1a22 0%, #15151c 100%); border-radius: 10px; padding: 18px 22px; display: flex; align-items: center; gap: 18px; margin: 12px 0 28px; }
  .hero-icon { font-size: 38px; }
  .hero-title { font-size: 18px; font-weight: 700; color: #fafafa; }
  .hero-detail { font-size: 13px; color: #a4a4b4; margin-top: 3px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
  .card { background: #15151c; border: 1px solid #24242d; border-radius: 8px; padding: 12px 14px; }
  .card.muted { opacity: 0.55; }
  .card .label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; font-weight: 600; }
  .card .value { font-size: 16px; font-weight: 600; margin-top: 4px; }
  .card .sub { font-size: 12px; color: #888; margin-top: 4px; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
  table { width: 100%; border-collapse: collapse; background: #15151c; border-radius: 8px; overflow: hidden; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #24242d; font-size: 13px; vertical-align: top; }
  th { background: #1a1a22; font-weight: 600; color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
  tr:last-child td { border-bottom: none; }

  .add-form { display: flex; gap: 8px; align-items: center; margin-top: 10px; padding: 12px; background: #15151c; border: 1px dashed #2a2a34; border-radius: 8px; flex-wrap: wrap; }
  .add-form > b { color: #aaa; font-size: 13px; margin-right: 4px; }
  .add-form input, .add-form select, .inline-form input { background: #1a1a22; color: #e4e4ea; border: 1px solid #2a2a34; border-radius: 5px; padding: 6px 10px; font-size: 13px; min-width: 120px; }
  button { background: #2a2a34; color: #e4e4ea; border: 1px solid #3a3a44; border-radius: 5px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-weight: 500; }
  button:hover { background: #333340; }
  button.primary { background: #2d5ea8; border-color: #3d6eb8; color: white; }
  button.primary:hover { background: #3566b4; }
  button.danger { background: #6a2323; border-color: #8a3333; color: #ffd0d0; }
  button.danger:hover { background: #7a2d2d; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }
  label input { background: #1a1a22; color: #e4e4ea; border: 1px solid #2a2a34; border-radius: 5px; padding: 6px 10px; font-size: 13px; }

  details.inline-form { display: inline-block; }
  details.inline-form summary { cursor: pointer; color: #aaa; padding: 4px 8px; border-radius: 4px; list-style: none; font-size: 12px; }
  details.inline-form summary:hover { background: #1a1a22; color: white; }
  details.inline-form form { display: flex; gap: 4px; margin-top: 6px; }
  details.inline-form input { width: 100px; }

  .settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .settings-grid form { background: #15151c; border: 1px solid #24242d; border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 10px; }

  .badge { background: #2d5ea8; color: white; font-size: 10px; padding: 1px 6px; border-radius: 8px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }

  /* Save toast */
  .toast {
    position: fixed; top: 22px; right: 22px;
    background: #2d7a2d; color: white; font-weight: 600; font-size: 13px;
    padding: 10px 18px; border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.4);
    transition: opacity 0.6s ease, transform 0.6s ease;
    z-index: 1000;
  }
  .toast-fade { opacity: 0; transform: translateY(-8px); }

  /* Section head with top-right action button */
  .section-head { display: flex; justify-content: flex-end; margin-bottom: 10px; }
  .btn-add { font-size: 13px; padding: 7px 14px; }

  /* Medications table */
  .meds-table { table-layout: fixed; }
  .meds-table td.nowrap { color: #c4a3ff; font-family: "SF Mono", ui-monospace, monospace; font-size: 12px; }
  .meds-actions { display: flex; gap: 6px; justify-content: flex-end; align-items: center; }
  .meds-actions form { margin: 0; display: inline; }

  /* Modal dialog */
  dialog.med-dialog {
    background: #15151c; color: #e4e4ea;
    border: 1px solid #2a2a34; border-radius: 10px;
    padding: 22px 24px; min-width: 400px; max-width: 540px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  }
  dialog.med-dialog::backdrop { background: rgba(5,5,10,0.72); backdrop-filter: blur(2px); }
  dialog.med-dialog h3 { margin: 0 0 16px; font-size: 16px; font-weight: 700; color: #fafafa; }
  dialog.med-dialog form { display: flex; flex-direction: column; gap: 14px; }
  dialog.med-dialog label {
    display: flex; flex-direction: column; gap: 6px;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #888; font-weight: 600;
  }
  dialog.med-dialog label input, dialog.med-dialog label select {
    background: #1a1a22; color: #e4e4ea; border: 1px solid #2a2a34;
    padding: 8px 10px; border-radius: 5px; font-size: 14px; text-transform: none;
  }
  dialog.med-dialog label input:focus { outline: none; border-color: #3d6eb8; }

  .time-rows { display: flex; flex-direction: column; gap: 6px; }
  .time-row { display: flex; gap: 6px; align-items: center; }
  .time-row select {
    flex: 1; background: #1a1a22; color: #e4e4ea; border: 1px solid #2a2a34;
    padding: 7px 10px; border-radius: 5px; font-size: 13px;
  }
  .btn-icon { padding: 4px 10px; font-size: 14px; line-height: 1; }
  .btn-small { align-self: flex-start; font-size: 12px; padding: 4px 10px; margin-top: 4px; }

  .dialog-actions {
    display: flex; justify-content: flex-end; gap: 8px;
    margin-top: 4px; padding-top: 14px; border-top: 1px solid #24242d;
  }

  select { background: #1a1a22; color: #e4e4ea; border: 1px solid #2a2a34; border-radius: 5px; padding: 6px 10px; font-size: 13px; }

  .job-group { margin-bottom: 18px; }
  .job-group-title { font-size: 13px; font-weight: 700; color: #c4a3ff; margin-bottom: 6px; letter-spacing: 0.02em; }
  .badge-type { background: #24242d; color: #c4a3ff; font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }

  .events-list { display: flex; flex-direction: column; gap: 2px; }
  .event-row { display: grid; grid-template-columns: 82px 32px 1fr; gap: 10px; padding: 8px 12px; background: #15151c; border-bottom: 1px solid #1f1f28; align-items: flex-start; }
  .event-row:first-child { border-radius: 8px 8px 0 0; }
  .event-row:last-child { border-radius: 0 0 8px 8px; border-bottom: none; }
  .event-ts { font: 12px/1.3 "SF Mono", ui-monospace, monospace; color: #888; padding-top: 4px; }
  .event-icon { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; color: white; margin-top: 2px; }
  .event-title { font-weight: 600; font-size: 13px; }
  .event-summary { font-size: 12px; color: #9f9faf; margin-top: 2px; }
"""


def _navbar(family_id: str, active: str) -> str:
    home_cls = "active" if active == "home" else ""
    meds_cls = "active" if active == "medications" else ""
    settings_cls = "active" if active == "settings" else ""
    return f"""
    <nav class="navbar">
      <div class="brand">AI-Care</div>
      <a href="/admin/{escape(family_id)}" class="{home_cls}">Home</a>
      <a href="/admin/{escape(family_id)}/medications" class="{meds_cls}">Medications</a>
      <a href="/admin/{escape(family_id)}/settings" class="{settings_cls}">Settings</a>
    </nav>"""


def _page_shell(family: dict, state: str, missing: list[str], active: str, content: str) -> str:
    fam_id = family["id"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>AI-Care · {escape(active)}</title>
<style>{_STYLES}</style>
</head>
<body>
  {_navbar(fam_id, active)}
  <div class="header-row">
    <div>
      <h1>AI-Care <span class="muted" style="font-weight:400">· family</span> <code>{escape(fam_id[:8])}</code> {_state_chip(state, missing)}</h1>
      <div class="muted">last refreshed: {escape(datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S'))} {escape(_tz_label())}</div>
    </div>
  </div>
  {content}
</body>
</html>"""


def _render_home(**ctx) -> str:
    family = ctx["family"]

    content = f"""
  <h2>Roles</h2>
  <div class="grid">
    {_user_card(ctx['parent'], 'Parent')}
    {_user_card(ctx['on_duty_today'], 'On duty today')}
  </div>

  {_status_hero(ctx["status"])}

  <h2>Scheduled jobs ({len(ctx['family_jobs'])})</h2>
  {_jobs_table(ctx['family_jobs'])}

  <h2>Recent events — last 24h ({len(ctx['events'])})</h2>
  {_events_timeline(ctx['events'], ctx['user_by_id'])}"""

    return _page_shell(family, ctx["state"], ctx["missing"], "home", content)


def _render_medications(**ctx) -> str:
    family = ctx["family"]
    fam_id = family["id"]

    content = f"""
  <h2>Medications</h2>
  {_meds_section(fam_id, ctx['meds'])}"""

    return _page_shell(family, ctx["state"], ctx["missing"], "medications", content)


def _render_settings(**ctx) -> str:
    family = ctx["family"]
    fam_id = family["id"]
    caregivers = [u for u in ctx["all_users"] if u["role"] == "caregiver"]

    toast = '<div class="toast" id="save-toast">✓ Saved</div>' if ctx.get("saved") else ""

    content = f"""
  {toast}
  <h2>Caregivers & parent</h2>
  {_users_section(fam_id, ctx['all_users'], family.get('primary_caregiver_user_id'))}

  <h2>Rotation</h2>
  {_rotation_section(fam_id, ctx['rotation'], ctx['user_by_id'], caregivers, ctx['today_dow'])}

  <h2>Family settings</h2>
  {_settings_section(fam_id, family)}

  <h2>Onboarding tokens</h2>
  {_handshake_section(fam_id, caregivers)}

  <script>
    (function() {{
      const t = document.getElementById('save-toast');
      if (!t) return;
      setTimeout(() => t.classList.add('toast-fade'), 2200);
      setTimeout(() => t.remove(), 3000);
    }})();
  </script>"""

    return _page_shell(family, ctx["state"], ctx["missing"], "settings", content)
