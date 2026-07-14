"""CardDAV sync bridge — pushes household contacts from PostgreSQL to Radicale as VCards."""
from __future__ import annotations

import asyncio
import logging
import re
from uuid import UUID
from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

import httpx

from .config import settings

log = logging.getLogger("nova-core.carddav")


# ── VCF helpers ─────────────────────────────────────────────


def _escape_vcf(text: str | None) -> str:
    """Escape VCF-special characters per RFC 6350 section 3.2."""
    if text is None:
        return ""
    s = text.replace("\\", "\\\\")
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\n", "\\n ")
    return s


def _build_vcard(contact: dict[str, Any]) -> str:
    """Build a VCF 3.0 string from a contact dict."""
    name = contact.get("name") or ""
    first = name.split(" ", 1)[0] if " " in name else name
    last = name.split(" ", 1)[1] if " " in name else ""

    uid = str(contact["id"])
    rev_raw = contact.get("updated_at")
    if rev_raw:
        rev = rev_raw.isoformat() if hasattr(rev_raw, "isoformat") else str(rev_raw)
    else:
        rev = datetime.now(timezone.utc).isoformat()

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "PRODID:-//Nova//Household//EN",
        f"FN:{_escape_vcf(name)}",
        f"N:{_escape_vcf(last)};{_escape_vcf(first)};;;",
        f"UID:{uid}",
        f"REV:{rev}",
    ]

    for email in contact.get("emails") or []:
        t = email.get("type") or ""
        if t:
            lines.append(f"EMAIL;TYPE={t}:{email['email']}")
        else:
            lines.append(f"EMAIL:{email['email']}")

    for phone in contact.get("phones") or []:
        t = phone.get("type") or ""
        if t:
            lines.append(f"TEL;TYPE={t}:{phone['phone']}")
        else:
            lines.append(f"TEL:{phone['phone']}")

    for addr in contact.get("addresses") or []:
        t = addr.get("type") or ""
        escaped = _escape_vcf(addr["address"])
        if t:
            lines.append(f"ADR;TYPE={t}:;;{escaped};;;;")
        else:
            lines.append(f"ADR:;;{escaped};;;;")

    notes = contact.get("notes")
    if notes:
        lines.append(f"NOTE:{_escape_vcf(notes)}")

    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def _parse_vcard_uid(vcf_text: str) -> str | None:
    m = re.search(r"^UID:(.+)$", vcf_text, re.MULTILINE)
    return m.group(1).strip() if m else None


# ── CardDAV client ──────────────────────────────────────────


_address_book_path: str | None = None


def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.caldav_url.rstrip("/"),
        auth=httpx.BasicAuth(settings.caldav_username, settings.caldav_password),
        timeout=httpx.Timeout(10.0),
    )


async def _ensure_address_book(client: httpx.AsyncClient) -> str:
    global _address_book_path
    if _address_book_path is not None:
        return _address_book_path

    # PROPFIND root for addressbook-home-set
    body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <c:addressbook-home-set/>
  </d:prop>
</d:propfind>"""
    resp = await client.request("PROPFIND", "/", data=body, headers={"Depth": "0"})
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:carddav"}
    home_set = root.find(".//c:addressbook-home-set/d:href", ns)
    if home_set is None:
        raise RuntimeError("CardDAV: no addressbook-home-set in response")
    home_href = home_set.text

    # PROPFIND home set for existing address books
    body2 = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:resourcetype/>
    <d:displayname/>
  </d:prop>
</d:propfind>"""
    resp2 = await client.request("PROPFIND", home_href, data=body2, headers={"Depth": "1"})
    resp2.raise_for_status()

    root2 = ET.fromstring(resp2.text)
    for response in root2.findall(".//d:response", ns):
        resourcetype = response.find(".//d:resourcetype", ns)
        if resourcetype is not None and resourcetype.find("c:addressbook", ns) is not None:
            displayname = response.find(".//d:displayname", ns)
            if displayname is not None and displayname.text == "Nova Household":
                href = response.find("d:href", ns)
                if href is not None:
                    _address_book_path = href.text
                    return _address_book_path

    # Create address book
    mkcol_body = """<?xml version="1.0" encoding="utf-8"?>
<d:mkcol xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:set>
    <d:prop>
      <d:resourcetype>
        <d:collection/>
        <c:addressbook/>
      </d:resourcetype>
      <d:displayname>Nova Household</d:displayname>
    </d:prop>
  </d:set>
</d:mkcol>"""
    mkcol_resp = await client.request("MKCOL", home_href.rstrip("/") + "/nova-household", data=mkcol_body)
    mkcol_resp.raise_for_status()

    _address_book_path = home_href.rstrip("/") + "/nova-household/"
    return _address_book_path


# ── Sync operations ─────────────────────────────────────────


async def sync_contact(contact_id: str | UUID) -> bool:
    try:
        from .contacts import get_contact

        contact = await get_contact(contact_id)
        if contact is None:
            return False

        vcard = _build_vcard(dict(contact))
        async with _get_client() as client:
            ab_path = await _ensure_address_book(client)
            put_resp = await client.put(
                f"{ab_path}{contact_id}.vcf",
                content=vcard,
                headers={"Content-Type": "text/vcard; charset=utf-8"},
            )
            return put_resp.is_success
    except (httpx.HTTPError, Exception) as exc:
        log.warning("CardDAV sync_contact failed for %s: %s", contact_id, exc)
        return False


async def delete_contact_vcard(contact_id: str | UUID) -> bool:
    try:
        async with _get_client() as client:
            ab_path = await _ensure_address_book(client)
            del_resp = await client.delete(f"{ab_path}{contact_id}.vcf")
            return del_resp.is_success or del_resp.status_code == 404
    except (httpx.HTTPError, Exception) as exc:
        log.warning("CardDAV delete_contact_vcard failed for %s: %s", contact_id, exc)
        return False


async def sync_all_contacts() -> dict[str, int]:
    from .contacts import list_contacts

    all_contacts = await list_contacts()
    synced = 0
    failed = 0

    async with _get_client() as client:
        ab_path = await _ensure_address_book(client)
        for contact in all_contacts:
            try:
                vcard = _build_vcard(contact)
                put_resp = await client.put(
                    f"{ab_path}{contact['id']}.vcf",
                    content=vcard,
                    headers={"Content-Type": "text/vcard; charset=utf-8"},
                )
                if put_resp.is_success:
                    synced += 1
                else:
                    failed += 1
                    log.warning("CardDAV sync failed for %s: HTTP %s", contact["id"], put_resp.status_code)
            except Exception as exc:
                failed += 1
                log.warning("CardDAV sync exception for %s: %s", contact["id"], exc)

    return {"synced": synced, "failed": failed, "total": len(all_contacts)}
