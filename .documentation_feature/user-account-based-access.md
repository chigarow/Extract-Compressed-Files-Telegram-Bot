# User Account Based Access

## Overview
Runs as a Telegram user (not bot) so all uploads/downloads use higher user limits and interactive chat. Target recipient is controlled via config to prevent unintended forwarding.

## Key Files & Components
- `utils/constants.py`: Loads `API_ID`, `API_HASH`, and `TARGET_USERNAME` from `secrets.properties`; raises if missing.
- `utils/telegram_operations.py`: `get_client()` builds Telethon client/session scoped to a user account and resolves `TARGET_USERNAME` entity.
- `secrets.properties`: stores credentials including `ACCOUNT_B_USERNAME` that acts as the authorized recipient.

## Process Flow
1. On startup, constants validate presence of API credentials and `TARGET_USERNAME` and create data directories.
2. Telethon client signs in as the user account using saved session or interactive prompts.
3. Incoming messages are processed only from the configured sender (see sender validation feature) and forwarded/uploads target the resolved `TARGET_USERNAME` entity.
4. User identity persists via `data/session.session`, enabling headless restarts without re-login.

## Edge Cases & Safeguards
- Missing or blank credentials cause `RuntimeError` early, avoiding partially initialized runs.
- Username comparison is case-insensitive and tolerates `@` prefix when validating senders.
- If the target username cannot be resolved (renamed/deleted), uploads will fail early with logging so the operator can update `secrets.properties`.

## Operational Notes
- Changing `ACCOUNT_B_USERNAME` requires restarting to reload constants.
- Session files may contain sensitive data; restrict filesystem access on shared hosts.
