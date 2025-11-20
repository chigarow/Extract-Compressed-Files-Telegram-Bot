# Sender Validation & Security

## Overview
Only processes messages from the configured `ACCOUNT_B_USERNAME`, blocking and logging everything else to prevent unauthorized control of the bot.

## Key Files & Components
- `utils/constants.py`: loads `TARGET_USERNAME`/`ACCOUNT_B_USERNAME` and raises if missing.
- `extract-compressed-files.py`: early sender checks compare incoming message sender to configured username (case-insensitive, `@` ignored).
- `readme.md` Security section documents protected command surfaces and logging messages.

## Process Flow
1. Every incoming event extracts the sender username/id.
2. Username is normalized (lowercased, stripped of `@`) and compared against `TARGET_USERNAME`.
3. If mismatch, message is ignored for replies and a warning is logged with sender details; processing stops.
4. If match, message is processed (commands, downloads, etc.) normally.

## Edge Cases & Safeguards
- Users without usernames (ID-only) are rejected to avoid ambiguous access.
- Ensures commands, uploads, Torbox links, and password prompts all require auth; there is no bypass path.
- Logging provides audit trail of blocked attempts without revealing responses to unauthorized users.

## Operational Notes
- Update `ACCOUNT_B_USERNAME` in `secrets.properties` if your target user renames their account; restart required.
- Keep logs secure since they may contain sender identifiers of blocked attempts.
