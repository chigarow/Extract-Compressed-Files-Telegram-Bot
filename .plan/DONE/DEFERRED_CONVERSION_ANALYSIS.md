# Deferred Video Conversion Analysis & Implementation Plan

## Problem Analysis

### Current Issues from Logs

```
2025-11-22 14:54:37,528 - ERROR - Video compression timed out
2025-11-22 14:54:37,557 - INFO - Cleaned up timed-out compression file
2025-11-22 15:04:47,713 - ERROR - Video compression timed out
2025-11-22 15:06:03,036 - WARNING - ⚠️ File missing before upload: ...compressed.mp4
2025-11-22 15:16:27,406 - ERROR - Grouped media upload failed: The provided media object is invalid
```

### Root Causes

1. **Blocking Compression**: Video conversion happens synchronously during upload, blocking the entire upload queue
2. **Timeout Issues**: Large videos timeout (300s default), causing file cleanup and upload failures
3. **Missing Files**: Compressed files are cleaned up on timeout but still referenced in upload tasks
4. **Invalid Media Errors**: Some videos are incompatible with Telegram's format requirements
5. **No Resume Support**: Crashed conversions restart from scratch, wasting time and resources

## Solution: Deferred Video Conversion System

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Upload Queue Processing                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Normal Files (Images, Compatible Videos)                 │
│     ├─> Upload immediately                                   │
│     └─> Mark as complete                                     │
│                                                               │
│  2. Incompatible Videos                                      │
│     ├─> Detect incompatibility                              │
│     ├─> Create deferred_conversion task                     │
│     ├─> Move to END of upload queue                         │
│     └─> Continue with other files                           │
│                                                               │
│  3. After All Normal Uploads Complete                        │
│     ├─> Process deferred_conversion tasks                   │
│     ├─> Convert videos with state saving                    │
│     ├─> Resume on crash                                     │
│     └─> Upload converted files                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

#### 1. **Non-Blocking Conversion**
- Normal uploads proceed without waiting for video conversion
- Incompatible videos queued for later processing
- No timeout blocking during main upload flow

#### 2. **Crash-Resilient State Saving**
```python
# Conversion state saved to disk
{
    "file_path": "/path/to/video.mov",
    "output_path": "/path/to/video_converted.mp4",
    "status": "in_progress",  # pending, in_progress, completed, failed
    "progress": 45,  # percentage
    "started_at": 1234567890,
    "last_updated": 1234567891,
    "retry_count": 0
}
```

#### 3. **Automatic Resume**
- On crash: Check for incomplete conversions
- Resume from last checkpoint if possible
- Restart from beginning if resume fails
- Preserve original file until conversion succeeds

#### 4. **Priority System**
```
Priority 1: Images (no conversion needed)
Priority 2: Compatible videos (no conversion needed)
Priority 3: Incompatible videos (deferred conversion)
```

## Implementation Plan

### Phase 1: Core Infrastructure (High Priority)

#### 1.1 Add Configuration Constants
```python
# utils/constants.py
DEFERRED_VIDEO_CONVERSION = True  # Enable deferred conversion
CONVERSION_STATE_FILE = os.path.join(DATA_DIR, 'conversion_state.json')
RECOVERY_DIR = os.path.join(DATA_DIR, 'recovery')  # For converted files
QUARANTINE_DIR = os.path.join(DATA_DIR, 'quarantine')  # For failed files
```

#### 1.2 Create Conversion State Manager
```python
# utils/conversion_state.py
class ConversionStateManager:
    """Manages state for video conversions with crash recovery"""
    
    def save_state(self, file_path, status, progress, output_path)
    def load_state(self, file_path)
    def mark_completed(self, file_path)
    def mark_failed(self, file_path, error)
    def get_incomplete_conversions()
    def cleanup_completed()
```

#### 1.3 Enhance Queue Manager
```python
# utils/queue_manager.py

async def _execute_upload_task(self, task):
    """Enhanced with deferred conversion support"""
    
    # Check if video needs conversion
    if is_video and not is_telegram_compatible(file_path):
        # Create deferred conversion task
        deferred_task = {
            'type': 'deferred_conversion',
            'file_path': file_path,
            'filename': filename,
            'archive_name': archive_name,
            'extraction_folder': extraction_folder,
            'retry_count': 0
        }
        
        # Add to END of queue (after all normal uploads)
        await self.add_upload_task(deferred_task)
        
        # Skip this file for now
        logger.info(f"⏸️ Deferred video conversion: {filename}")
        return

async def _execute_deferred_conversion(self, task):
    """Process deferred conversion after all normal uploads"""
    
    # Wait for all normal uploads to complete
    if self._has_pending_priority_work():
        # Re-queue at end
        await self.upload_queue.put(task)
        return
    
    # Start conversion with state saving
    converted_path = await self._convert_with_state_saving(task)
    
    if converted_path:
        # Queue upload of converted file
        upload_task = {
            'type': 'direct_media',
            'file_path': converted_path,
            'filename': os.path.basename(converted_path),
            'archive_name': task.get('archive_name'),
            'cleanup_after_upload': [task['file_path']]  # Clean original
        }
        await self.add_upload_task(upload_task)
```

### Phase 2: State-Saving Conversion (High Priority)

#### 2.1 Enhanced Video Conversion
```python
# utils/media_processing.py

async def convert_video_with_state_saving(
    input_path: str,
    output_path: str,
    state_manager: ConversionStateManager
) -> str:
    """Convert video with intermediate state saving"""
    
    # Check for existing partial conversion
    state = state_manager.load_state(input_path)
    
    if state and state['status'] == 'in_progress':
        # Try to resume
        if os.path.exists(state['output_path']):
            logger.info(f"♻️ Resuming conversion: {input_path}")
            # Attempt resume (if ffmpeg supports it)
            # Otherwise restart from beginning
    
    # Save initial state
    state_manager.save_state(
        file_path=input_path,
        status='in_progress',
        progress=0,
        output_path=output_path
    )
    
    try:
        # Run conversion with progress tracking
        result = await compress_video_for_telegram(
            input_path,
            output_path,
            progress_callback=lambda p: state_manager.save_state(
                input_path, 'in_progress', p, output_path
            )
        )
        
        if result:
            state_manager.mark_completed(input_path)
            return result
        else:
            state_manager.mark_failed(input_path, "Conversion failed")
            return None
            
    except Exception as e:
        state_manager.mark_failed(input_path, str(e))
        raise
```

### Phase 3: Crash Recovery (High Priority)

#### 3.1 Startup Recovery Check
```python
# extract-compressed-files.py

async def recover_incomplete_conversions():
    """Check for and resume incomplete conversions on startup"""
    
    state_manager = ConversionStateManager()
    incomplete = state_manager.get_incomplete_conversions()
    
    if incomplete:
        logger.info(f"🔄 Found {len(incomplete)} incomplete conversions")
        
        for conversion in incomplete:
            file_path = conversion['file_path']
            
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ Original file missing: {file_path}")
                state_manager.mark_failed(file_path, "File missing")
                continue
            
            # Queue for deferred conversion
            deferred_task = {
                'type': 'deferred_conversion',
                'file_path': file_path,
                'filename': os.path.basename(file_path),
                'retry_count': conversion.get('retry_count', 0)
            }
            
            queue_manager = get_queue_manager()
            await queue_manager.add_upload_task(deferred_task)
            
            logger.info(f"♻️ Queued recovery conversion: {file_path}")
```

### Phase 4: Testing & Validation (Critical)

#### 4.1 Unit Tests
```python
# tests/test_deferred_conversion.py

class TestDeferredConversion:
    def test_incompatible_video_detection()
    def test_deferred_task_creation()
    def test_priority_ordering()
    def test_state_saving()
    def test_crash_recovery()
    def test_conversion_resume()
    def test_fallback_to_restart()
```

#### 4.2 Integration Tests
```python
# tests/test_deferred_conversion_integration.py

async def test_full_workflow():
    """Test complete deferred conversion workflow"""
    
    # 1. Upload archive with mixed media
    # 2. Verify images upload first
    # 3. Verify compatible videos upload second
    # 4. Verify incompatible videos deferred
    # 5. Verify conversions start after normal uploads
    # 6. Verify converted files upload successfully
```

## Configuration

### secrets.properties
```ini
# Deferred Video Conversion
DEFERRED_VIDEO_CONVERSION=true  # Enable deferred conversion
CONVERSION_TIMEOUT_SECONDS=1800  # 30 minutes for large files
CONVERSION_MAX_RETRIES=3  # Max retry attempts
CONVERSION_STATE_SAVE_INTERVAL=10  # Save state every 10 seconds
```

## Benefits

### 1. **No Upload Blocking**
- Images and compatible videos upload immediately
- No waiting for slow video conversions
- Better user experience

### 2. **Crash Resilience**
- Conversions resume after crashes
- No wasted processing time
- Automatic recovery on restart

### 3. **Better Resource Management**
- Conversions happen when system is idle
- No memory buildup from parallel conversions
- Optimal for low-resource devices (Termux)

### 4. **Production Ready**
- Comprehensive error handling
- State persistence
- Automatic cleanup
- Full test coverage

## Migration Path

### Step 1: Enable Feature Flag
```python
DEFERRED_VIDEO_CONVERSION = False  # Start disabled
```

### Step 2: Deploy Infrastructure
- Add state manager
- Update queue manager
- Add recovery logic

### Step 3: Test Thoroughly
- Run unit tests
- Run integration tests
- Test crash scenarios

### Step 4: Enable in Production
```python
DEFERRED_VIDEO_CONVERSION = True  # Enable after testing
```

## Monitoring

### Key Metrics
- Number of deferred conversions
- Conversion success rate
- Average conversion time
- Recovery success rate
- Disk space usage

### Logging
```
INFO: ⏸️ Deferred video conversion: video.mov (incompatible format)
INFO: 🎬 Starting deferred conversion: video.mov
INFO: 💾 Conversion state saved: video.mov (45% complete)
INFO: ✅ Conversion completed: video.mov -> video_converted.mp4
INFO: ♻️ Resumed conversion after crash: video.mov (from 45%)
```

## Rollback Plan

If issues occur:
1. Set `DEFERRED_VIDEO_CONVERSION=false`
2. Complete any in-progress conversions
3. Revert to synchronous conversion
4. Investigate and fix issues
5. Re-enable after fixes

## Timeline

- **Week 1**: Phase 1 (Core Infrastructure)
- **Week 2**: Phase 2 (State-Saving Conversion)
- **Week 3**: Phase 3 (Crash Recovery)
- **Week 4**: Phase 4 (Testing & Validation)
- **Week 5**: Production Deployment

## Success Criteria

✅ No upload blocking during video conversion
✅ Conversions resume after crashes
✅ All tests passing (unit + integration)
✅ Production deployment successful
✅ Zero data loss
✅ Improved user experience
