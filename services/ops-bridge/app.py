"""ops-bridge: OpenObserve alert webhook → Forgejo issue.

Closed-loop incident intake. OpenObserve alert destinations POST here; the
bridge fingerprints the alert, dedups against open issues, and either creates
a new Forgejo issue (labeled incident/monitoring/auto-heal) or comments on the
existing one. Users file issues on the same repo manually — both streams end
up in one queue that ops/triage.sh consumes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

log = logging.getLogger("ops-bridge")
logging.basicConfig(level=logging.INFO)

FORGEJO_URL = os.environ.get("FORGEJO_URL", "https://git.7rb.nl").rstrip("/")
FORGEJO_REPO = os.environ.get("FORGEJO_REPO", "ruben/nova")
FORGEJO_TOKEN = os.environ.get("FORGEJO_TOKEN", "")
BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "")
ALERT_LABELS = [
    l.strip()
    for l in os.environ.get("BRIDGE_ALERT_LABELS", "incident,monitoring,auto-heal").split(",")
    if l.strip()
]

API = f"{FORGEJO_URL}/api/v1/repos/{FORGEJO_REPO}"
HEADERS = {"Authorization": f"token {FORGEJO_TOKEN}"}

app = FastAPI(title="Nova ops-bridge", version="0.1.0")

_label_ids: dict[str, int] = {}  # name -> id cache


async def _resolve_label_ids(client: httpx.AsyncClient, names: list[str]) -> list[int]:
    """Forgejo's create-issue API wants numeric label IDs; resolve and cache."""
    missing = [n for n in names if n not in _label_ids]
    if missing:
        resp = await client.get(f"{API}/labels", headers=HEADERS, params={"limit": 100})
        resp.raise_for_status()
        for label in resp.json():
            _label_ids[label["name"]] = label["id"]
    unknown = [n for n in names if n not in _label_ids]
    if unknown:
        log.warning("labels missing on repo (run ops/issue.sh setup-labels): %s", unknown)
    return [_label_ids[n] for n in names if n in _label_ids]


def _fingerprint(alert_name: str, stream: str) -> str:
    return hashlib.sha1(f"{alert_name}|{stream}".encode()).hexdigest()[:10]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "repo": FORGEJO_REPO}


@app.post("/webhooks/openobserve")
async def openobserve_alert(
    request: Request,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    if not BRIDGE_TOKEN or x_bridge_token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="bad or missing X-Bridge-Token")

    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode(errors="replace")}

    alert_name = str(payload.get("alert_name") or payload.get("name") or "unnamed-alert")
    stream = str(payload.get("stream_name") or payload.get("stream") or "unknown-stream")
    fp = _fingerprint(alert_name, stream)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    detail_block = (
        f"**Alert:** {alert_name}\n"
        f"**Stream:** {stream}\n"
        f"**Fired at:** {now}\n"
        f"**Fingerprint:** `{fp}`\n\n"
        "<details><summary>Full alert payload</summary>\n\n"
        f"```json\n{json.dumps(payload, indent=2, default=str)[:6000]}\n```\n"
        "</details>"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        # Dedup: is there already an open issue for this fingerprint?
        search = await client.get(
            f"{API}/issues",
            headers=HEADERS,
            params={"state": "open", "q": fp, "type": "issues"},
        )
        search.raise_for_status()
        existing = search.json()

        if existing:
            issue = existing[0]
            await client.post(
                f"{API}/issues/{issue['number']}/comments",
                headers=HEADERS,
                json={"body": f"⚠️ Alert fired again at {now}.\n\n{detail_block}"},
            )
            log.info("alert %s deduped onto issue #%s", fp, issue["number"])
            return {"action": "commented", "issue": issue["number"]}

        label_ids = await _resolve_label_ids(client, ALERT_LABELS)
        resp = await client.post(
            f"{API}/issues",
            headers=HEADERS,
            json={
                "title": f"[monitoring] {alert_name} on {stream} ({fp})",
                "body": detail_block,
                "labels": label_ids,
            },
        )
        resp.raise_for_status()
        number = resp.json()["number"]
        log.info("alert %s → new issue #%s", fp, number)
        return {"action": "created", "issue": number}
