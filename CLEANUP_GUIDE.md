# Cleanup and Monitoring Features

This document describes the cleanup and monitoring features added to the Extract Compressed Files Telegram Bot.

## Overview

The bot now includes automatic file organization and manual cleanup commands to help manage disk space and keep the data directory organized.

## File Organization Structure

### Directory Structure
```
data/
├── torbox/              # Dedicated directory for Torbox downloads
├── *.json               # Queue and state files (preserved during cleanup)
├── session.session      # Telegram session (preserved during cleanup)
└── [temp files]         # Temporary extraction and processing files
```

### TORBOX_DIR
All Torbox downloads are now saved to `data/torbox/` instead of cluttering the main data directory. This separation:
- Keeps the main data directory clean
- Makes it easier to manage Torbox-specific files
- Improves overall file organization

## Cleanup Commands

### `/cleanup [hours]`
Remove old files from the data directory.

**Usage:**
```
/cleanup          # Remove files older than 24 hours (default)
/cleanup 48       # Remove files older than 48 hours
/cleanup 72       # Remove files older than 72 hours
```

**What it does:**
- Scans the data directory for old files
- Shows you how many files will be removed
- Asks for confirmation before deletion
- Preserves important files (JSON queues, session files)
- Reports total space recovered

**Protected Files:**
The following files are never removed:
- `processed_archives.json`
- `download_queue.json`
- `upload_queue.json`
- `retry_queue.json`
- `current_process.json`
- `session.session`

**Confirmation Required:**
After running `/cleanup`, you must confirm with `/confirm-cleanup` to actually delete the files.

### `/cleanup-orphans`
Remove orphaned extraction directories that are no longer being processed.

**Usage:**
```
/cleanup-orphans
```

**What it does:**
- Identifies extraction directories older than 1 hour
- Removes directories that match extraction patterns:
  - Contains "extract" in the name
  - Contains "_files" in the name
  - Has a long name (>20 characters)
- Reports how much space was recovered

**No Confirmation Required:**
This command executes immediately since it only removes temporary extraction directories.

### `/confirm-cleanup`
Confirm and execute a pending cleanup operation.

**Usage:**
```
/confirm-cleanup
```

**What it does:**
- Executes the cleanup operation you previously initiated with `/cleanup`
- Reports how many files were removed and space recovered
- Clears the pending cleanup

**Note:** This command only works after you've run `/cleanup` first.

## Monitoring Script

A system monitoring script is available to analyze disk usage and file organization.

### Running the Monitor

```bash
python3 monitor_system.py
```

### What the Monitor Shows

The monitoring script provides:

1. **DATA Directory Statistics**
   - Total size and file count
   - Subdirectory breakdown with sizes

2. **TORBOX Directory Statistics**
   - Dedicated Torbox storage analysis
   - File counts and sizes

3. **Old Files Analysis**
   - Files older than 24 hours
   - Total size that could be recovered
   - Top 5 largest old files

4. **Extraction Directories Analysis**
   - Orphaned extraction directories
   - Age and size of each directory
   - Cleanup candidates

5. **Recommendations**
   - Actionable suggestions based on current state
   - Estimated space recovery
   - Maintenance reminders

### Example Output

```
================================================================================
FILE ORGANIZATION PERFORMANCE REPORT
Generated: 2025-01-11 16:30:00
================================================================================

📊 DATA DIRECTORY: /path/to/data
--------------------------------------------------------------------------------
Total Size:       2.45 GB
Total Files:      156
Subdirectories:   3

📁 Subdirectory Breakdown:
Directory                      Size            Files     
--------------------------------------------------------------------------------
torbox                         1.89 GB         42        
old_extraction                 350.00 MB       89        

📦 TORBOX DIRECTORY: /path/to/data/torbox
--------------------------------------------------------------------------------
Total Size:       1.89 GB
Total Files:      42
Subdirectories:   2

🕐 OLD FILES ANALYSIS (>24 hours)
--------------------------------------------------------------------------------
Old Files:        23
Total Size:       567.00 MB
Avg Age:          3.2 days

📂 EXTRACTION DIRECTORIES ANALYSIS
--------------------------------------------------------------------------------
Extraction Dirs:  2
Total Size:       450.00 MB

⚠️  2 directories eligible for cleanup (>1 hour old)
   Potential space recovery: 450.00 MB

💡 RECOMMENDATIONS
--------------------------------------------------------------------------------
  🧹 Run /cleanup to remove 23 old files and recover 567.00 MB
  🧹 Run /cleanup-orphans to remove 2 directories and recover 450.00 MB
```

## Integration Tests

Comprehensive integration tests are available to validate cleanup functionality.

### Running Integration Tests

```bash
python3 run_integration_tests.py
```

### Tests Included

1. **Command Handler Tests**
   - Validates all cleanup commands are properly imported
   - Checks that handlers are callable

2. **Old File Cleanup Tests**
   - Creates old test files (48 hours old)
   - Verifies they are removed by cleanup
   - Confirms file count reporting is accurate

3. **Recent File Preservation Tests**
   - Creates recent test files
   - Verifies they are NOT removed by cleanup
   - Ensures proper age threshold enforcement

4. **Orphaned Directory Cleanup Tests**
   - Creates extraction-like directories
   - Timestamps them as old (>1 hour)
   - Verifies they are identified and removed

5. **TORBOX_DIR Structure Tests**
   - Validates TORBOX_DIR exists
   - Confirms proper path configuration

## Technical Implementation

### Event Handling Fixes

The cleanup implementation includes robust event handling to prevent crashes:

- **Event Validation**: All `event.reply()` calls are wrapped with validation checks
- **Serialization Safety**: Handles both live event objects and serialized dictionaries
- **Graceful Fallbacks**: Logs to console when events are unavailable
- **Error Recovery**: Comprehensive try-catch blocks prevent cascading failures

### File Safety Mechanisms

Multiple safety mechanisms protect important files:

1. **Protected File List**: Hard-coded list of files that are never deleted
2. **Age Thresholds**: Only remove files older than specified time
3. **Confirmation Workflow**: Manual cleanup requires explicit confirmation
4. **Directory Exclusions**: Skips hidden directories and protected folders

### Performance Considerations

The implementation is designed for efficiency:

- **Single Pass Scanning**: Files are scanned once per cleanup operation
- **Size Reporting**: Pre-calculates space recovery before deletion
- **Minimal I/O**: Uses efficient directory walking algorithms
- **Error Tolerance**: Individual file errors don't stop the entire cleanup

## Best Practices

### Regular Maintenance

For best results:

1. **Run monitoring weekly** to check disk usage
2. **Run cleanup monthly** if you process many files
3. **Check orphaned directories** after bot crashes or restarts
4. **Monitor TORBOX_DIR** to ensure downloads are completing

### Troubleshooting

If cleanup isn't working:

1. Check file permissions in the data directory
2. Verify the bot has write access
3. Look for error messages in the bot logs
4. Run `monitor_system.py` to diagnose issues

### Safety Tips

- Always review monitoring output before running cleanup
- Start with longer age thresholds (e.g., 72 hours) if unsure
- Keep backups of important files outside the data directory
- Test cleanup with small age thresholds in a test environment first

## Future Enhancements

Potential improvements for future versions:

1. **Automated Cleanup Scheduling**
   - Automatic cleanup at specified intervals
   - Configurable age thresholds
   - Background cleanup without user intervention

2. **Advanced Filtering**
   - Cleanup by file type
   - Size-based cleanup (remove largest files first)
   - Selective directory cleanup

3. **Statistics Dashboard**
   - Historical disk usage tracking
   - Cleanup operation history
   - Space recovery metrics

4. **Smart Cleanup**
   - Machine learning-based orphan detection
   - Automatic threshold adjustment based on usage patterns
   - Predictive space management

## Support

For issues or questions about cleanup functionality:

1. Check the bot logs for error messages
2. Run `monitor_system.py` to diagnose
3. Review this documentation
4. Check the changelog in `.history/` directory

## Changelog

See `.history/2025-01-11_comprehensive_fixes_and_cleanup.md` for detailed implementation history and technical notes.
