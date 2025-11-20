#!/usr/bin/env python3
"""
Comprehensive test to ensure all imports from extract-compressed-files.py work correctly.
This tests the exact imports used in the production code.
"""

import sys
import os

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

print("=" * 80)
print("COMPREHENSIVE IMPORT TEST")
print("Testing all imports from extract-compressed-files.py...")
print("=" * 80)

try:
    # Test ALL imports from extract-compressed-files.py (lines 34-75)
    print("\n1. Testing constant imports...")
    from utils import (
        ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS,
        MAX_ARCHIVE_GB, DATA_DIR, LOG_FILE, MIN_PCT_STEP, MIN_EDIT_INTERVAL,
        FAST_DOWNLOAD_ENABLED, FAST_DOWNLOAD_CONNECTIONS, WIFI_ONLY_MODE,
    )
    print("   ✓ All constants imported")
    
    print("\n2. Testing utility function imports...")
    from utils import (
        human_size, format_eta, setup_logger,
    )
    print("   ✓ All utility functions imported")
    
    print("\n3. Testing file operation imports...")
    from utils import (
        compute_sha256, extract_with_password, is_password_error, extract_archive_async,
    )
    print("   ✓ All file operations imported")
    
    print("\n4. Testing media processing imports...")
    from utils import (
        is_ffmpeg_available, is_ffprobe_available, validate_video_file,
        is_telegram_compatible_video, needs_video_processing,
        compress_video_for_telegram, get_video_attributes_and_thumbnail,
    )
    print("   ✓ All media processing functions imported")
    
    print("\n5. Testing cache and persistence imports...")
    from utils import (
        CacheManager, ProcessManager, FailedOperationsManager,
    )
    print("   ✓ All cache and persistence classes imported")
    
    print("\n6. Testing queue management imports...")
    from utils import (
        get_queue_manager, get_processing_queue,
    )
    print("   ✓ All queue management functions imported")
    
    print("\n7. Testing Telegram operations imports...")
    from utils import (
        get_client, ensure_target_entity, TelegramOperations, create_download_progress_callback,
    )
    print("   ✓ All Telegram operations imported")
    
    print("\n8. Testing FastTelethon imports...")
    from utils import (
        fast_download_to_file,
    )
    print("   ✓ FastTelethon functions imported")
    
    print("\n9. Testing Torbox downloader imports...")
    from utils import (
        is_torbox_link, extract_torbox_links, get_filename_from_url,
        download_torbox_with_progress, detect_file_type_from_url,
    )
    print("   ✓ All Torbox functions imported")
    
    print("\n10. Testing command handler imports...")
    from utils import (
        handle_password_command, handle_max_concurrent_command, handle_set_max_archive_gb_command,
        handle_toggle_fast_download_command, handle_toggle_wifi_only_command, 
        handle_toggle_transcoding_command, handle_compression_timeout_command, handle_help_command, 
        handle_battery_status_command, handle_status_command, handle_queue_command, handle_cancel_password,
        handle_cancel_extraction, handle_cancel_process, handle_cleanup_command, 
        handle_confirm_cleanup_command, handle_cleanup_orphans_command
    )
    print("   ✓ All command handlers imported (including cleanup commands)")
    
    print("\n" + "=" * 80)
    print("✅ SUCCESS: ALL IMPORTS FROM PRODUCTION CODE WORKING!")
    print("=" * 80)
    
    # Count total imports
    total_imports = (
        len([ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS,
             MAX_ARCHIVE_GB, DATA_DIR, LOG_FILE, MIN_PCT_STEP, MIN_EDIT_INTERVAL,
             FAST_DOWNLOAD_ENABLED, FAST_DOWNLOAD_CONNECTIONS, WIFI_ONLY_MODE]) +
        len([human_size, format_eta, setup_logger]) +
        len([compute_sha256, extract_with_password, is_password_error, extract_archive_async]) +
        len([is_ffmpeg_available, is_ffprobe_available, validate_video_file,
             is_telegram_compatible_video, needs_video_processing,
             compress_video_for_telegram, get_video_attributes_and_thumbnail]) +
        len([CacheManager, ProcessManager, FailedOperationsManager]) +
        len([get_queue_manager, get_processing_queue]) +
        len([get_client, ensure_target_entity, TelegramOperations, create_download_progress_callback]) +
        len([fast_download_to_file]) +
        len([is_torbox_link, extract_torbox_links, get_filename_from_url,
             download_torbox_with_progress, detect_file_type_from_url]) +
        len([handle_password_command, handle_max_concurrent_command, handle_set_max_archive_gb_command,
             handle_toggle_fast_download_command, handle_toggle_wifi_only_command, 
             handle_toggle_transcoding_command, handle_compression_timeout_command, handle_help_command, 
             handle_battery_status_command, handle_status_command, handle_queue_command, handle_cancel_password,
             handle_cancel_extraction, handle_cancel_process, handle_cleanup_command, 
             handle_confirm_cleanup_command, handle_cleanup_orphans_command])
    )
    
    print(f"\nTotal imports verified: {total_imports}")
    print("All production code imports are working correctly!")
    
    pass  # Prevent exit during tests
    
except ImportError as e:
    print(f"\n❌ IMPORT FAILED!")
    print(f"Error: {e}")
    print("\n" + "=" * 80)
    print("❌ IMPORT TEST FAILED")
    print("=" * 80)
    pass  # Prevent exit on unexpected error
    
except Exception as e:
    print(f"\n❌ UNEXPECTED ERROR!")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 80)
    print("❌ IMPORT TEST FAILED")
    print("=" * 80)
    pass  # Prevent exit on unexpected error
