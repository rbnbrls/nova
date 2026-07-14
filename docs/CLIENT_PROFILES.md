# Client Profiles — CalDAV/CardDAV Interoperability

## Server Details

| Field | Value |
|-------|-------|
| CalDAV URL (LAN) | `http://nova.local:5232/` |
| CardDAV URL (LAN) | `http://nova.local:5232/` |
| TLS-enabled URL | `https://nova.local/radicale/` |
| Username | `CALDAV_USERNAME` env var |
| Password | `CALDAV_PASSWORD` env var |
| Auth method | Basic Auth (over HTTPS) |
| Note | Endpoints are LAN-only — not exposed to the public internet. |

---

## Nextcloud Setup

### Calendar

1. Open the Calendar app in Nextcloud.
2. Click **+ Add calendar** → **From link**.
3. Set **URL** to `http://nova.local:5232/`.
4. Set **Display name** to `Nova Household`.
5. Enter the `CALDAV_USERNAME` and `CALDAV_PASSWORD` credentials.
6. Click **Connect**.

### Contacts (CardDAV)

1. Open the Contacts app in Nextcloud.
2. Click **+ New address book** → **From URL**.
3. Set **URL** to `http://nova.local:5232/`.
4. Enter the `CALDAV_USERNAME` and `CALDAV_PASSWORD` credentials.
5. Click **Connect**.

---

## Apple Devices (macOS / iOS)

Apple requires HTTPS for CalDAV/CardDAV accounts. Caddy provides TLS termination
at `https://nova.local/radicale/` using its internal CA.

### macOS — Calendar

1. Open **System Settings** → **Internet Accounts**.
2. Click **Add Account** → **Other** → **CalDAV Account**.
3. Fill in:
   - **Server**: `nova.local`
   - **Path**: `/radicale/`
   - **Port**: `443`
   - **Use SSL**: ON
   - **Username**: `CALDAV_USERNAME`
   - **Password**: `CALDAV_PASSWORD`
4. Click **Sign In**.

### macOS — Contacts

1. Open **System Settings** → **Internet Accounts**.
2. Click **Add Account** → **Other** → **CardDAV Account**.
3. Fill in:
   - **Server**: `nova.local`
   - **Path**: `/radicale/`
   - **Port**: `443`
   - **Use SSL**: ON
   - **Username**: `CALDAV_USERNAME`
   - **Password**: `CALDAV_PASSWORD`
4. Click **Sign In**.

### iOS — Calendar & Contacts

1. Open **Settings** → **Apps** → **Calendar** → **Accounts** → **Add Account** → **Other**.
2. Choose **Add CalDAV Account** or **Add CardDAV Account**.
3. Fill in the same server, path, port, SSL, username, and password as above.

### Trusting Caddy's Internal CA

Caddy's internal CA is auto-generated. To avoid SSL warnings, export and trust it:

```bash
# Export Caddy's root CA from the running container
docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > /tmp/caddy-root.crt

# On macOS, add to system keychain (requires admin)
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/caddy-root.crt
```

After trusting the CA, restart the Calendar/Contacts app.

---

## Windows / Thunderbird Setup

Windows Calendar does not natively support CalDAV. Use Mozilla Thunderbird instead.

### Thunderbird — Calendar

1. Open Thunderbird.
2. **File** → **New** → **Calendar**.
3. Select **On the Network** → **CalDAV**.
4. **Location**: `http://nova.local:5232/`
5. Enter `CALDAV_USERNAME` and `CALDAV_PASSWORD`.
6. Click **Finish**.

### Thunderbird — Address Book

1. Open Thunderbird.
2. **File** → **New** → **CardDAV Address Book**.
3. **URL**: `http://nova.local:5232/`
4. Enter `CALDAV_USERNAME` and `CALDAV_PASSWORD`.
5. Click **Finish**.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 Unauthorized | Wrong username/password | Check `CALDAV_USERNAME` / `CALDAV_PASSWORD` env vars |
| 404 Not Found | Wrong URL path | Use `http://nova.local:5232/` (port 5232) or `https://nova.local/radicale/` |
| Connection refused | Radicale container not running | `docker compose up -d radicale` |
| SSL errors | Caddy CA not trusted | Trust Caddy's root CA (see above) or use HTTP on port 5232 for LAN clients |
| Empty calendar/contacts | No data synced yet | Nova syncs contacts on startup, on CRUD, and every 15 minutes. Add a contact via Nova first. |
| PROPFIND fails | Proxy misconfiguration | Verify `Caddyfile` has `handle_path /radicale/* { reverse_proxy radicale:5232 }` |
| Slow sync | Large address book | Radicale is filesystem-backed. Sync is incremental — only changed contacts are pushed. |

---

## Architecture Notes

- **Radicale** runs standalone on port `5232`, independent of Nova's LLM runtime.
- **Caddy** provides TLS termination via the `/radicale/` path prefix on `nova.local`.
- **Data flow is one-way**: Nova PostgreSQL → Radicale. Changes made directly in Radicale will be overwritten by the next Nova sync.
- **Sync triggers**:
  - On Nova Core startup (all contacts)
  - On every contact CRUD operation (the affected contact only)
  - Every 15 minutes via APScheduler (full sync)
- **Authentication**: Single shared credential (`CALDAV_USERNAME` / `CALDAV_PASSWORD`) for all household members — same LAN-trust model as the admin panel.
