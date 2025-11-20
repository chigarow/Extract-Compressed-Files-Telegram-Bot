# Configurable Limits

## Overview
Allows runtime-adjustable limits for archive size, disk space safety, and concurrency through commands and config values.

## Key Files & Components
- `utils/constants.py`: reads `MAX_ARCHIVE_GB`, `DISK_SPACE_FACTOR`, `MAX_CONCURRENT`, etc., from config.
- `utils/command_handlers.py`: `/set_max_archive_gb`, `/max_concurrent`, `/toggle_fast_download`, `/toggle_wifi_only`, `/toggle_transcoding`, `/compression-timeout` commands update config and globals.
- `config.py`: persists changes back to `secrets.properties` via `config.save()`.

## Process Flow
1. On startup, limits load from `secrets.properties` into `config` then constants.
2. User issues commands to adjust limits; handlers update `config._config` and save to disk.
3. Global variables (e.g., semaphore) are refreshed to reflect new limits immediately.
4. Subsequent tasks honor updated thresholds for validation and download/upload sizing.

## Edge Cases & Safeguards
- Handlers validate presence of `DEFAULT` section before writing to config to avoid key errors.
- Invalid values raise exceptions caught and reported back via chat without crashing the bot.
- Archive size checks occur before download/extraction to avoid wasting bandwidth.

## Operational Notes
- After editing `secrets.properties` manually, restart the bot to reload static constants.
- Keep `MAX_CONCURRENT` low on Termux to avoid memory pressure; defaults favor sequential safety.
