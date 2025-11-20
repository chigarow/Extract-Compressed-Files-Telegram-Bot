# Network Monitoring

## Overview
Detects connection type (WiFi vs mobile vs ethernet) and enforces WiFi-only mode when configured, pausing downloads on mobile data to save bandwidth.

## Key Files & Components
- `utils/network_monitor.py`: `NetworkMonitor` class checks interfaces/routes/dumpsys to classify connections and triggers callbacks.
- `utils/constants.py`: `WIFI_ONLY_MODE` flag from config controls whether mobile data is allowed.
- `extract-compressed-files.py`: registers callbacks to pause/resume downloads depending on network state.

## Process Flow
1. Monitor polls connection type on an interval (default 10s) using multiple detection strategies for Android/Linux.
2. On changes, it fires callbacks such as `wifi_connected`, `mobile_detected`, or `disconnected`.
3. When WiFi-only is enabled and mobile is detected, download tasks are paused/deferred until WiFi returns.
4. Once WiFi resumes, queued tasks continue automatically.

## Edge Cases & Safeguards
- Falls back across several detection methods to handle Termux and standard Linux; errors are logged but do not crash the loop.
- If connection is unknown, the monitor opts for caution (may pause downloads when WiFi-only) to avoid unintended mobile usage.
- Disconnection events can trigger retry/backoff logic elsewhere; monitor simply reports state.

## Operational Notes
- Toggle WiFi-only at runtime with `/toggle_wifi_only`; setting persists in `secrets.properties`.
- Adjust `check_interval` when constructing `NetworkMonitor` if you need more/less frequent checks.
