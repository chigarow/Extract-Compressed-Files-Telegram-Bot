# Efficient Storage Management

## Overview
Minimizes disk usage on low-resource devices by deleting source archives and extracted files after successful uploads, while keeping recovery data safe.

## Key Files & Components
- `utils/queue_manager.py`: `ExtractionCleanupRegistry` and `ArchiveCleanupRegistry` track when uploads finish and trigger folder/archive cleanup.
- `extract-compressed-files.py`: orchestrates cleanup after each processing pipeline completes.
- `utils/constants.py`: defines `DATA_DIR`, `RECOVERY_DIR`, and `QUARANTINE_DIR` for controlled deletion.

## Process Flow
1. Extraction registers output folder and batch counts with cleanup registries.
2. As batches upload, registries decrement counters; once all files from an archive are uploaded, cleanup tasks remove extraction folders and source archives.
3. Special recovery/quarantine paths are excluded from automated deletion to preserve problematic files for debugging.

## Edge Cases & Safeguards
- Cleanup only fires after all grouped uploads complete to avoid removing files still in use.
- Errors during deletion are logged but do not halt the bot; manual cleanup can be triggered via cleanup commands.
- Recovery directories are protected to avoid losing files needed for retries or diagnostics.

## Operational Notes
- Disk space checks use `config.disk_space_factor` to ensure enough free space before extraction; adjust in `secrets.properties`/config.
- On Termux, consider external storage permissions if data directory is moved.
