"""
Cache and persistence manager for the Telegram Compressed File Extractor.
Handles file processing cache, queues, and other persistent data.
"""

import os
import json
import asyncio
import logging
from .constants import (
    PROCESSED_CACHE_PATH, DOWNLOAD_QUEUE_FILE, UPLOAD_QUEUE_FILE,
    CURRENT_PROCESS_FILE, FAILED_OPERATIONS_FILE
)

logger = logging.getLogger('extractor')


class CacheManager:
    """Manages all cache and persistent data operations."""
    
    def __init__(self):
        self.processed_cache = {}
        self.cache_lock = asyncio.Lock()
        self.load_processed_cache()
    
    def load_processed_cache(self):
        """Load processed files cache from disk."""
        if os.path.exists(PROCESSED_CACHE_PATH):
            try:
                with open(PROCESSED_CACHE_PATH, 'r') as f:
                    self.processed_cache = json.load(f)
                logger.info(f"Loaded {len(self.processed_cache)} processed file records")
            except Exception as e:
                logger.error(f"Failed to load processed cache: {e}")
                self.processed_cache = {}
    
    async def save_cache(self):
        """Save processed files cache to disk."""
        async with self.cache_lock:
            tmp_path = PROCESSED_CACHE_PATH + '.tmp'
            try:
                with open(tmp_path, 'w') as f:
                    json.dump(self.processed_cache, f, indent=2)
                os.replace(tmp_path, PROCESSED_CACHE_PATH)
            except Exception as e:
                logger.error(f"Failed to save cache: {e}")
    
    async def add_to_cache(self, file_hash: str, info: dict):
        """Add file information to processed cache."""
        async with self.cache_lock:
            self.processed_cache[file_hash] = info
        await self.save_cache()
    
    def is_processed(self, filename: str, size: int) -> bool:
        """Check if a file has already been processed."""
        for file_hash, info in self.processed_cache.items():
            if info.get('filename') == filename and info.get('size') == size:
                return True
        return False
    
    def is_hash_processed(self, file_hash: str) -> bool:
        """Check if a file hash has already been processed."""
        return file_hash in self.processed_cache


class PersistentQueue:
    """Manages persistent queues for downloads and uploads."""
    
    def __init__(self, queue_file: str):
        self.queue_file = queue_file
        self.queue_data = []
        self.load_queue()
    
    def load_queue(self):
        """Load queue from disk."""
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    self.queue_data = json.load(f)
                logger.info(f"Loaded {len(self.queue_data)} items from {self.queue_file}")
            except Exception as e:
                logger.error(f"Failed to load queue from {self.queue_file}: {e}")
                self.queue_data = []
    
    def save_queue(self):
        """Save queue to disk."""
        try:
            tmp_path = self.queue_file + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(self.queue_data, f, indent=2)
            os.replace(tmp_path, self.queue_file)
        except Exception as e:
            logger.error(f"Failed to save queue to {self.queue_file}: {e}")
    
    def add_item(self, item: dict):
        """Add item to queue."""
        self.queue_data.append(item)
        self.save_queue()
    
    def remove_item(self, item: dict):
        """Remove item from queue."""
        if item in self.queue_data:
            self.queue_data.remove(item)
            self.save_queue()
    
    def get_items(self) -> list:
        """Get all items in queue."""
        return self.queue_data.copy()
    
    def clear(self):
        """Clear all items from queue."""
        self.queue_data.clear()
        self.save_queue()


class ProcessManager:
    """Manages current process state for crash recovery."""
    
    def __init__(self):
        self.current_download_process = None
        self.current_upload_process = None
        self.load_current_processes()
    
    def load_current_processes(self):
        """Load current processes from disk."""
        if os.path.exists(CURRENT_PROCESS_FILE):
            try:
                with open(CURRENT_PROCESS_FILE, 'r') as f:
                    data = json.load(f)
                    self.current_download_process = data.get('download_process')
                    self.current_upload_process = data.get('upload_process')
                logger.info("Loaded current process state")
            except Exception as e:
                logger.error(f"Failed to load current processes: {e}")
    
    def save_current_processes(self):
        """Save current processes to disk."""
        try:
            data = {
                'download_process': self.current_download_process,
                'upload_process': self.current_upload_process
            }
            tmp_path = CURRENT_PROCESS_FILE + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, CURRENT_PROCESS_FILE)
        except Exception as e:
            logger.error(f"Failed to save current processes: {e}")
    
    async def update_download_process(self, process_info: dict):
        """Update current download process."""
        self.current_download_process = process_info
        self.save_current_processes()
    
    async def update_upload_process(self, process_info: dict):
        """Update current upload process."""
        self.current_upload_process = process_info
        self.save_current_processes()
    
    async def clear_download_process(self):
        """Clear current download process."""
        self.current_download_process = None
        self.save_current_processes()
    
    async def clear_upload_process(self):
        """Clear current upload process."""
        self.current_upload_process = None
        self.save_current_processes()


class FailedOperationsManager:
    """Manages failed operations for retry."""
    
    def __init__(self):
        self.failed_operations = []
        self.load_failed_operations()
    
    def load_failed_operations(self):
        """Load failed operations from disk."""
        if os.path.exists(FAILED_OPERATIONS_FILE):
            try:
                with open(FAILED_OPERATIONS_FILE, 'r') as f:
                    self.failed_operations = json.load(f)
                logger.info(f"Loaded {len(self.failed_operations)} failed operations for retry")
            except Exception as e:
                logger.error(f"Failed to load failed operations: {e}")
                self.failed_operations = []
    
    def save_failed_operations(self):
        """Save failed operations to disk."""
        try:
            tmp_path = FAILED_OPERATIONS_FILE + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(self.failed_operations, f, indent=2)
            os.replace(tmp_path, FAILED_OPERATIONS_FILE)
        except Exception as e:
            logger.error(f"Failed to save failed operations: {e}")
    
    def add_failed_operation(self, operation: dict):
        """Add a failed operation for retry."""
        self.failed_operations.append(operation)
        self.save_failed_operations()
    
    def remove_failed_operation(self, operation: dict):
        """Remove a failed operation after successful retry."""
        if operation in self.failed_operations:
            self.failed_operations.remove(operation)
            self.save_failed_operations()
    
    def get_failed_operations(self) -> list:
        """Get all failed operations."""
        return self.failed_operations.copy()
    
    def clear_all(self):
        """Clear all failed operations."""
        self.failed_operations.clear()
        self.save_failed_operations()
