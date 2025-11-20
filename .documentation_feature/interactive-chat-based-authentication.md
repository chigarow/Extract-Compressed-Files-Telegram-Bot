# Interactive Chat-Based Authentication

## Overview
Provides first-run login through Telegram chat instead of terminal input so the daemon can run headless (Termux/servers) and still receive phone/code/password prompts.

## Key Files & Components
- `extract-compressed-files.py`: `create_interactive_login_handlers()` builds phone/code/password callbacks and drives message prompts to `Saved Messages`.
- `utils/telegram_operations.py`: wraps Telethon client creation (`get_client`) and authentication helpers, persisting session to `data/session.session`.
- `data/session.session`: Telethon session cache for reuse across restarts.

## Process Flow
1. Script starts and initializes `login_state` plus Telethon `client` via `get_client`.
2. When Telethon requests phone/code/password, the corresponding callback in `create_interactive_login_handlers()` sets `login_state['waiting_for']`, messages `me`, and awaits a future.
3. User replies in chat; message handler resolves the future, returns value to Telethon, and continues sign-in.
4. On success, Telethon writes session to `data/session.session` so subsequent runs skip prompts.

## Edge Cases & Safeguards
- Handles 2FA passwords through the same chat flow; failures are logged and the prompt is reissued.
- If Telegram blocks message sending (e.g., connectivity issues), login request is logged and awaiting state stays set until a reply arrives.
- Session reuse avoids repeated prompts; deleting `data/session.session` forces re-auth.
- Phone/code format is not strictly validated, but unexpected replies keep the future pending, so the user can retry without restarting.

## Operational Notes
- Requires `APP_API_ID`/`APP_API_HASH` in `secrets.properties`; missing values raise at import in `utils/constants.py`.
- Keep `data/` writable so Telethon can persist the session; otherwise authentication would repeat every run.
