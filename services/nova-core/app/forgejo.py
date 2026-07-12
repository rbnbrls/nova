"""Forgejo API client for maintenance job issue tracking.

Follows the same httpx + token-auth + label-resolution pattern as
services/ops-bridge/app.py, but designed for in-process use from
scheduler jobs inside nova-core.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("nova-core")


class ForgejoError(Exception):
    """Raised when a Forgejo API call fails."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Forgejo API error {status_code}: {message}")


class ForgejoClient:
    """Async Forgejo API client.

    Provides issue CRUD, label management, and label-ID resolution
    with caching — suitable for use from APScheduler jobs.
    """

    def __init__(self, base_url: str, repo: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._repo = repo
        self._token = token
        self._api_base = f"{self._base_url}/api/v1/repos/{self._repo}"
        self._headers = {"Authorization": f"token {self._token}"}
        self._label_ids: dict[str, int] = {}  # name -> id cache

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _api(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Call the Forgejo REST API with auth and rate-limit delay."""
        url = f"{self._api_base}/{path.lstrip('/')}"
        log.debug("Forgejo API %s %s", method.upper(), url)

        await asyncio.sleep(1)  # rate-limit guard

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=self._headers, json=json, params=params
            )

        if resp.status_code >= 400:
            log.warning("Forgejo API %s %s failed: %s", method.upper(), url, resp.status_code)
            raise ForgejoError(status_code=resp.status_code, message=resp.text)

        return resp

    async def _resolve_label_ids(self, names: list[str]) -> list[int]:
        """Resolve label names to numeric IDs, caching results.

        Follows the same approach as ops-bridge's _resolve_label_ids.
        """
        missing = [n for n in names if n not in self._label_ids]
        if missing:
            resp = await self._api("GET", "labels", params={"limit": 100})
            for label in resp.json():
                self._label_ids[label["name"]] = label["id"]

        unknown = [n for n in names if n not in self._label_ids]
        if unknown:
            log.warning("Forgejo labels missing on repo: %s", unknown)

        return [self._label_ids[n] for n in names if n in self._label_ids]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> int:
        """Create a new issue. Returns the issue number."""
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            label_ids = await self._resolve_label_ids(labels)
            payload["labels"] = label_ids

        resp = await self._api("POST", "issues", json=payload)
        number: int = resp.json()["number"]
        log.info("Forgejo issue #%d created: %s", number, title)
        return number

    async def comment_issue(self, issue_number: int, body: str) -> None:
        """Add a comment to an existing issue."""
        await self._api(
            "POST", f"issues/{issue_number}/comments", json={"body": body}
        )
        log.debug("Commented on issue #%d", issue_number)

    async def close_issue(self, issue_number: int) -> None:
        """Close an issue by setting state to 'closed'."""
        await self._api(
            "PATCH", f"issues/{issue_number}", json={"state": "closed"}
        )
        log.info("Closed issue #%d", issue_number)

    async def add_label(self, issue_number: int, label: str) -> None:
        """Add a single label to an issue."""
        label_ids = await self._resolve_label_ids([label])
        if not label_ids:
            log.warning("Cannot add label '%s' — not found on repo", label)
            return
        await self._api(
            "POST", f"issues/{issue_number}/labels", json={"labels": label_ids}
        )
        log.debug("Added label '%s' to issue #%d", label, issue_number)

    async def remove_label(self, issue_number: int, label: str) -> None:
        """Remove a single label from an issue by name."""
        resp = await self._api("GET", f"issues/{issue_number}/labels")
        for lbl in resp.json():
            if lbl["name"] == label:
                await self._api(
                    "DELETE", f"issues/{issue_number}/labels/{lbl['id']}"
                )
                log.debug("Removed label '%s' from issue #%d", label, issue_number)
                return
        log.warning("Label '%s' not found on issue #%d — nothing to remove", label, issue_number)

    async def open_issues_by_label(self, label: str) -> list[dict]:
        """List open issues filtered by a label name."""
        resp = await self._api(
            "GET", "issues", params={"state": "open", "labels": label, "type": "issues"}
        )
        return resp.json()
