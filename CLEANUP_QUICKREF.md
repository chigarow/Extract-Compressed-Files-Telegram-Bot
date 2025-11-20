# Quick Reference: Cleanup Commands

## Telegram Commands

### Remove Old Files
```
/cleanup          # Remove files older than 24 hours (default)
/cleanup 48       # Remove files older than 48 hours
/cleanup 72       # Remove files older than 3 days
```
⚠️ Requires confirmation with `/confirm-cleanup`

### Remove Orphaned Directories
```
/cleanup-orphans  # Remove extraction directories older than 1 hour
```
✅ Executes immediately

### Confirm Cleanup
```
/confirm-cleanup  # Execute pending cleanup operation
```

## Terminal Commands

### System Monitoring
```bash
python3 monitor_system.py
```
Shows:
- Total disk usage
- Old files (>24 hours)
- Orphaned directories
- Cleanup recommendations

### Run Tests
```bash
python3 run_integration_tests.py
```
Validates all cleanup functionality

### Basic Validation
```bash
python3 test_cleanup_validation.py
```
Quick sanity check

## Protected Files

These files are NEVER deleted by cleanup:
- `processed_archives.json`
- `download_queue.json`
- `upload_queue.json`
- `retry_queue.json`
- `current_process.json`
- `session.session`
- `data/torbox/` directory contents

## File Organization

```
data/
├── torbox/              # All Torbox downloads go here
├── *.json               # Queue files (protected)
├── session.session      # Telegram session (protected)
└── [temp files]         # Temporary files (can be cleaned)
```

## Best Practices

1. **Run monitoring first**
   ```bash
   python3 monitor_system.py
   ```

2. **Start with longer thresholds**
   ```
   /cleanup 72  # Start with 3 days
   ```

3. **Regular maintenance**
   - Monitor weekly
   - Cleanup monthly
   - Check orphans after crashes

4. **Safety first**
   - Review monitoring output before cleanup
   - Always confirm before deletion
   - Keep backups of important files

## Troubleshooting

### Cleanup Not Removing Files
1. Check file permissions
2. Verify bot has write access
3. Look for errors in logs
4. Run `monitor_system.py` to diagnose

### Files Still Present After Cleanup
- Files may be within the age threshold
- Files might be in protected list
- Check if files are locked by another process

### Space Not Being Recovered
- Orphaned directories need `/cleanup-orphans`
- Some files may be in `data/torbox/`
- Check monitoring report for recommendations

## Examples

### Typical Workflow
```bash
# 1. Check current state
python3 monitor_system.py

# 2. In Telegram, run cleanup
/cleanup 48

# 3. Review what will be deleted
# (bot will show count and size)

# 4. Confirm cleanup
/confirm-cleanup

# 5. Clean orphaned directories
/cleanup-orphans

# 6. Verify cleanup
python3 monitor_system.py
```

### After Bot Crash
```
/cleanup-orphans    # Remove leftover extraction directories
```

### Monthly Maintenance
```
/cleanup 720        # Remove files older than 30 days
/cleanup-orphans    # Clean up any leftovers
```

## Documentation

- **Full Guide**: `CLEANUP_GUIDE.md`
- **Session Notes**: `.history/2025-01-11_comprehensive_fixes_and_cleanup.md`
- **Main README**: `readme.md`

## Support

Questions? Check the documentation or review the monitoring script output for recommendations.
