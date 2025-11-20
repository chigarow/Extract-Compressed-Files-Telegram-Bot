# System Resource Monitoring

## Overview
Tracks CPU, memory, and disk usage in real time to provide insight into system load while processing files.

## Key Files & Components
- `utils/command_handlers.py`: status/help responses include system info pulled via `psutil` (imported in the module).
- `monitor_system.py`: standalone monitoring script that scans disk usage, old files, and cleanup recommendations.
- `utils/constants.py`: defines data directories whose usage is monitored.

## Process Flow
1. When responding to commands or logs, the code queries `psutil` to capture CPU/memory/disk stats.
2. `monitor_system.py` can be run to generate detailed reports on storage and aging files in `data/`.
3. Output helps decide when to run cleanup commands or adjust processing limits.

## Edge Cases & Safeguards
- If `psutil` is unavailable, imports would fail; ensure dependencies from `requirements.txt` are installed.
- Monitoring is read-only and does not alter files; cleanup actions are segregated into cleanup features.

## Operational Notes
- Run `python monitor_system.py` manually for detailed audits.
- Use cleanup commands to act on recommendations; see automatic file cleanup feature.
