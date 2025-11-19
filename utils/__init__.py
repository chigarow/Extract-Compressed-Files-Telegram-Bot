"""
Utils module for the Telegram Compressed File Extractor.

This module contains all utility functions organized by functionality:
- file_operations: File handling, extraction, compression
- media_processing: Video processing and media operations
- telegram_operations: Telegram client and API operations
- queue_manager: Queue management and processing coordination
- cache_manager: Cache handling and persistence
- command_handlers: Command handling functions
- utils: General utility functions
- constants: Application constants and configurations
- fast_download: FastTelethon parallel download implementation
- network_monitor: Network monitoring utilities
"""

# Import key modules for easy access
from .constants import *
from .utils import human_size, format_eta, setup_logger
from .file_operations import compute_sha256, extract_with_password, is_password_error, extract_archive_async
from .media_processing import (
    is_ffmpeg_available, is_ffprobe_available, validate_video_file,
    is_telegram_compatible_video, needs_video_processing,
    compress_video_for_telegram, get_video_attributes_and_thumbnail
)
from .cache_manager import CacheManager, PersistentQueue, ProcessManager, FailedOperationsManager
from .queue_manager import QueueManager, ProcessingQueue, get_queue_manager, get_processing_queue
from .telegram_operations import TelegramOperations, get_client, ensure_target_entity, create_download_progress_callback
from .fast_download import fast_download_to_file, fast_download_file
from .network_monitor import NetworkMonitor, NetworkType
from .command_handlers import (
    handle_password_command, handle_max_concurrent_command, handle_set_max_archive_gb_command,
    handle_toggle_fast_download_command, handle_toggle_wifi_only_command, 
    handle_toggle_transcoding_command, handle_compression_timeout_command, handle_help_command, 
    handle_battery_status_command, handle_status_command, handle_queue_command, 
    handle_cancel_password, handle_cancel_extraction, handle_cancel_process,
    handle_cleanup_command, handle_confirm_cleanup_command, handle_cleanup_orphans_command
)
from .torbox_downloader import (
    is_torbox_link, extract_torbox_links, get_filename_from_url, extract_file_id_from_url,
    download_from_torbox, download_torbox_with_progress, detect_file_type_from_url, get_torbox_metadata
)
from .streaming_extractor import StreamingExtractor, StreamingEntry, mark_streaming_entries_completed
from .webdav_client import (
    parse_webdav_url, get_webdav_client, reset_webdav_client,
    TorboxWebDAVClient, WebDAVItem, is_webdav_link, extract_webdav_links
)

__all__ = [
    'human_size', 'format_eta', 'setup_logger', 'compute_sha256', 'extract_with_password',
    'is_password_error', 'extract_archive_async', 'is_ffmpeg_available', 'is_ffprobe_available',
    'validate_video_file', 'is_telegram_compatible_video', 'needs_video_processing',
    'compress_video_for_telegram', 'get_video_attributes_and_thumbnail',
    'CacheManager', 'PersistentQueue', 'ProcessManager', 'FailedOperationsManager',
    'QueueManager', 'ProcessingQueue', 'get_queue_manager', 'get_processing_queue',
    'TelegramOperations', 'get_client', 'ensure_target_entity', 'create_download_progress_callback',
    'fast_download_to_file', 'fast_download_file', 'NetworkMonitor', 'NetworkType',
    'handle_password_command', 'handle_max_concurrent_command', 'handle_set_max_archive_gb_command',
    'handle_toggle_fast_download_command', 'handle_toggle_wifi_only_command', 
    'handle_toggle_transcoding_command', 'handle_compression_timeout_command', 'handle_help_command', 
    'handle_battery_status_command', 'handle_status_command', 'handle_queue_command', 
    'handle_cancel_password', 'handle_cancel_extraction', 'handle_cancel_process',
    'handle_cleanup_command', 'handle_confirm_cleanup_command', 'handle_cleanup_orphans_command',
    'is_torbox_link', 'extract_torbox_links', 'get_filename_from_url', 'extract_file_id_from_url',
    'download_from_torbox', 'download_torbox_with_progress', 'detect_file_type_from_url', 'get_torbox_metadata'
]

__all__ += [
    'StreamingExtractor', 'StreamingEntry', 'mark_streaming_entries_completed',
    'parse_webdav_url', 'get_webdav_client', 'reset_webdav_client',
    'TorboxWebDAVClient', 'WebDAVItem', 'is_webdav_link', 'extract_webdav_links'
]
