"""
Script to enable and test the deferred video conversion feature.
This script validates the implementation and runs comprehensive tests.
"""

import os
import sys
import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """Check if all required dependencies are available."""
    logger.info("🔍 Checking dependencies...")
    
    missing = []
    
    # Check Python version
    if sys.version_info < (3, 7):
        logger.error("❌ Python 3.7+ required")
        return False
    
    # Check required modules
    try:
        import pytest
        logger.info("✅ pytest available")
    except ImportError:
        missing.append("pytest")
    
    try:
        from PIL import Image
        logger.info("✅ Pillow available")
    except ImportError:
        missing.append("Pillow")
    
    # Check ffmpeg/ffprobe
    import shutil
    if shutil.which('ffmpeg'):
        logger.info("✅ ffmpeg available")
    else:
        logger.warning("⚠️  ffmpeg not found (optional but recommended)")
    
    if shutil.which('ffprobe'):
        logger.info("✅ ffprobe available")
    else:
        logger.warning("⚠️  ffprobe not found (optional but recommended)")
    
    if missing:
        logger.error(f"❌ Missing dependencies: {', '.join(missing)}")
        logger.info("Install with: pip install " + " ".join(missing))
        return False
    
    return True


def check_file_structure():
    """Check if all required files exist."""
    logger.info("🔍 Checking file structure...")
    
    required_files = [
        'utils/conversion_state.py',
        'utils/constants.py',
        'utils/queue_manager.py',
        'utils/media_processing.py',
        'tests/test_deferred_conversion.py'
    ]
    
    missing = []
    for file_path in required_files:
        if os.path.exists(file_path):
            logger.info(f"✅ {file_path}")
        else:
            logger.error(f"❌ {file_path} not found")
            missing.append(file_path)
    
    if missing:
        logger.error(f"❌ Missing files: {', '.join(missing)}")
        return False
    
    return True


def check_configuration():
    """Check configuration settings."""
    logger.info("🔍 Checking configuration...")
    
    try:
        from utils.constants import (
            DEFERRED_VIDEO_CONVERSION,
            CONVERSION_STATE_FILE,
            CONVERSION_MAX_RETRIES,
            RECOVERY_DIR,
            QUARANTINE_DIR
        )
        
        logger.info(f"✅ DEFERRED_VIDEO_CONVERSION = {DEFERRED_VIDEO_CONVERSION}")
        logger.info(f"✅ CONVERSION_STATE_FILE = {CONVERSION_STATE_FILE}")
        logger.info(f"✅ CONVERSION_MAX_RETRIES = {CONVERSION_MAX_RETRIES}")
        logger.info(f"✅ RECOVERY_DIR = {RECOVERY_DIR}")
        logger.info(f"✅ QUARANTINE_DIR = {QUARANTINE_DIR}")
        
        # Check if directories exist
        for dir_path in [RECOVERY_DIR, QUARANTINE_DIR]:
            if os.path.exists(dir_path):
                logger.info(f"✅ Directory exists: {dir_path}")
            else:
                logger.info(f"📁 Creating directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        return False


def run_tests():
    """Run unit tests for deferred conversion."""
    logger.info("🧪 Running unit tests...")
    
    try:
        import pytest
        
        # Run tests
        result = pytest.main([
            'tests/test_deferred_conversion.py',
            '-v',
            '--tb=short'
        ])
        
        if result == 0:
            logger.info("✅ All tests passed!")
            return True
        else:
            logger.error(f"❌ Tests failed with code {result}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test execution error: {e}")
        return False


def test_state_manager():
    """Test the conversion state manager."""
    logger.info("🧪 Testing ConversionStateManager...")
    
    try:
        from utils.conversion_state import ConversionStateManager
        import tempfile
        
        # Create temporary state file
        fd, temp_file = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        
        try:
            # Create state manager
            manager = ConversionStateManager(state_file=temp_file)
            
            # Test save state
            test_file = "/tmp/test_video.mov"
            manager.save_state(
                file_path=test_file,
                status='in_progress',
                progress=50,
                output_path="/tmp/test_video_converted.mp4"
            )
            logger.info("✅ State save successful")
            
            # Test load state
            state = manager.load_state(test_file)
            assert state is not None
            assert state['progress'] == 50
            logger.info("✅ State load successful")
            
            # Test mark completed
            manager.mark_completed(test_file)
            state = manager.load_state(test_file)
            assert state['status'] == 'completed'
            logger.info("✅ Mark completed successful")
            
            # Test stats
            stats = manager.get_stats()
            assert stats['completed'] == 1
            logger.info(f"✅ Stats: {stats}")
            
            logger.info("✅ ConversionStateManager tests passed!")
            return True
            
        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    except Exception as e:
        logger.error(f"❌ ConversionStateManager test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def show_usage_example():
    """Show usage example."""
    logger.info("\n" + "="*60)
    logger.info("📚 USAGE EXAMPLE")
    logger.info("="*60)
    
    example = """
# The deferred conversion feature is now enabled!

## How it works:

1. **Normal uploads proceed immediately**
   - Images upload without delay
   - Compatible videos upload without delay

2. **Incompatible videos are deferred**
   - Detected automatically during upload
   - Queued for conversion after normal uploads
   - No blocking of other files

3. **Conversions happen at the end**
   - After all normal uploads complete
   - With state saving for crash recovery
   - Automatic resume on restart

## Configuration (secrets.properties):

```ini
# Enable deferred conversion (default: true)
DEFERRED_VIDEO_CONVERSION=true

# Max conversion retries (default: 3)
CONVERSION_MAX_RETRIES=3

# Conversion timeout in seconds (default: 300)
COMPRESSION_TIMEOUT_SECONDS=1800  # 30 minutes for large files
```

## Monitoring:

Check conversion state:
```python
from utils.conversion_state import ConversionStateManager

manager = ConversionStateManager()
stats = manager.get_stats()
print(f"Conversions: {stats}")

incomplete = manager.get_incomplete_conversions()
print(f"Incomplete: {len(incomplete)}")
```

## Logs to watch for:

- ⏸️ Deferred video conversion: video.mov
- 🎬 Starting deferred conversion: video.mov
- 💾 Conversion state saved: video.mov (45%)
- ✅ Conversion completed: video.mov
- ♻️ Resumed conversion after crash: video.mov
"""
    
    print(example)


def main():
    """Main function."""
    logger.info("="*60)
    logger.info("🚀 DEFERRED VIDEO CONVERSION - SETUP & VALIDATION")
    logger.info("="*60)
    
    # Run checks
    checks = [
        ("Dependencies", check_dependencies),
        ("File Structure", check_file_structure),
        ("Configuration", check_configuration),
        ("State Manager", test_state_manager),
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {check_name}")
        logger.info(f"{'='*60}")
        
        if not check_func():
            all_passed = False
            logger.error(f"❌ {check_name} check failed!")
            break
        else:
            logger.info(f"✅ {check_name} check passed!")
    
    # Run full test suite if all checks passed
    if all_passed:
        logger.info(f"\n{'='*60}")
        logger.info("Running: Full Test Suite")
        logger.info(f"{'='*60}")
        
        if run_tests():
            logger.info("\n" + "="*60)
            logger.info("✅ ALL CHECKS PASSED!")
            logger.info("="*60)
            logger.info("\n🎉 Deferred video conversion is ready for production!")
            
            show_usage_example()
            
            return 0
        else:
            logger.error("\n" + "="*60)
            logger.error("❌ TEST SUITE FAILED")
            logger.error("="*60)
            return 1
    else:
        logger.error("\n" + "="*60)
        logger.error("❌ SETUP VALIDATION FAILED")
        logger.error("="*60)
        logger.error("\nPlease fix the issues above and try again.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
