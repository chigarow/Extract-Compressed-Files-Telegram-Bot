# System Monitoring Tools

## Overview
Includes standalone tooling to audit disk usage, identify old files, and recommend cleanup actions beyond the runtime status commands.

## Key Files & Components
- `monitor_system.py`: script that scans `data/` usage, lists old items, and prints cleanup suggestions.
- `utils/constants.py`: provides directory paths used by the monitor to focus on relevant locations.
- `CLEANUP_GUIDE.md`: explains how to interpret monitor outputs and act on them safely.

## Process Flow
1. Run `python monitor_system.py` manually; it gathers filesystem stats and inspects `data/` contents.
2. Report is output to stdout or log, highlighting large/old files and potential orphans.
3. User can then invoke cleanup commands or manual deletions informed by the report.

## Edge Cases & Safeguards
- Monitoring is read-only; it does not delete files, preventing accidental data loss.
- Handles missing directories gracefully by creating them or reporting emptiness.

## Operational Notes
- Useful on constrained Termux storage to identify when to offload or prune data.
- Combine with `run_all_tests.py`/`run_tests.py` before heavy cleanup to ensure functional state remains intact.
