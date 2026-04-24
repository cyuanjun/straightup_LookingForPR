"""Briefing storage: local filesystem paths + public URLs served through the tunnel."""

from __future__ import annotations

import secrets
from pathlib import Path

from app.config import settings

BRIEFINGS_DIR = Path("./cache/briefings")
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)


def new_token() -> str:
    """Random 12-char URL-safe token — the filename and the URL path segment."""
    return secrets.token_urlsafe(9)[:12]


def file_path(token: str) -> Path:
    return BRIEFINGS_DIR / f"{token}.pdf"


def public_base() -> str:
    """Public base URL of the tunnel — strips the /telegram suffix from WEBHOOK_URL."""
    url = (settings.webhook_url or "").rstrip("/")
    if url.endswith("/telegram"):
        url = url[: -len("/telegram")]
    return url


def public_url(token: str) -> str:
    return f"{public_base()}/briefings/{token}.pdf"


def list_recent(limit: int = 10) -> list[dict]:
    """Return most recent briefings (by mtime) with token, path, url, mtime."""
    if not BRIEFINGS_DIR.exists():
        return []
    files = [p for p in BRIEFINGS_DIR.glob("*.pdf") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        token = p.stem
        out.append(
            {
                "token": token,
                "path": p,
                "url": public_url(token),
                "mtime": p.stat().st_mtime,
                "size_kb": round(p.stat().st_size / 1024, 1),
            }
        )
    return out
