# FastTelethon parallel download implementation
# Based on https://gist.github.com/painor/7e74de80ae0c819d3e9abcf9989a8dd6
# Adapted for our extract-compressed-files.py use case

import asyncio
import logging
import math
import os
import time
import random
from collections import defaultdict
from typing import Optional, List, Union, Awaitable, DefaultDict, BinaryIO

from telethon import utils, helpers, TelegramClient
from telethon.crypto import AuthKey
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import (Document, InputFileLocation, InputDocumentFileLocation,
                               InputPhotoFileLocation, InputPeerPhotoFileLocation)
from telethon.errors import (
    FloodWaitError, TimeoutError, 
    ServerError, RPCError, AuthKeyError
)

# Import network monitoring if available
try:
    from .network_monitor import NetworkMonitor, NetworkType
    NETWORK_MONITOR_AVAILABLE = True
except ImportError:
    NETWORK_MONITOR_AVAILABLE = False
    NetworkMonitor = None
    NetworkType = None

log: logging.Logger = logging.getLogger("fast_download")

TypeLocation = Union[Document, InputDocumentFileLocation, InputPeerPhotoFileLocation,
                     InputFileLocation, InputPhotoFileLocation]


class DownloadSender:
    client: TelegramClient
    sender: MTProtoSender
    request: GetFileRequest
    remaining: int
    stride: int

    def __init__(self, client: TelegramClient, sender: MTProtoSender, file: TypeLocation, 
                 offset: int, limit: int, stride: int, count: int) -> None:
        self.sender = sender
        self.client = client
        self.request = GetFileRequest(file, offset=offset, limit=limit)
        self.stride = stride
        self.remaining = count

    async def next(self) -> Optional[bytes]:
        if not self.remaining:
            return None
        
        # Retry with exponential backoff
        max_retries = None  # Infinite retries
        base_delay = 1  # Start with 1 second
        max_delay = 300  # Max 5 minutes
        attempt = 0
        
        while True:
            try:
                result = await self.client._call(self.sender, self.request)
                self.remaining -= 1
                self.request.offset += self.stride
                return result.bytes
                
            except FloodWaitError as e:
                wait_time = e.seconds
                log.warning(f"Rate limited, waiting {wait_time} seconds")
                await asyncio.sleep(wait_time)
                attempt += 1
                continue
                
            except (TimeoutError, ServerError, OSError, Exception) as e:
                # OSError covers network connection issues, Exception catches other connectivity problems
                attempt += 1
                # Calculate delay with exponential backoff + jitter
                delay = min(base_delay * (2 ** min(attempt - 1, 10)), max_delay)
                jitter = random.uniform(0.5, 1.5)
                actual_delay = delay * jitter
                
                log.warning(f"Connection error (attempt {attempt}): {e}. Retrying in {actual_delay:.1f}s")
                await asyncio.sleep(actual_delay)
                
                # Try to reconnect sender after connection errors
                if isinstance(e, (OSError, TimeoutError)):
                    try:
                        await self.sender.disconnect()
                        # Recreate connection
                        dc = await self.client._get_dc(self.sender._dc_id if hasattr(self.sender, '_dc_id') else None)
                        await self.sender.connect(self.client._connection(
                            dc.ip_address, dc.port, dc.id,
                            loggers=self.client._log,
                            proxy=self.client._proxy
                        ))
                    except Exception as reconnect_error:
                        log.debug(f"Reconnection attempt failed: {reconnect_error}")
                
                continue
                
            except AuthKeyError as e:
                log.error(f"Auth key error, need to re-authenticate: {e}")
                raise  # Re-authentication required, don't retry
                
            except RPCError as e:
                if e.code in [500, 503]:  # Server errors that might be temporary
                    attempt += 1
                    delay = min(base_delay * (2 ** min(attempt - 1, 10)), max_delay)
                    jitter = random.uniform(0.5, 1.5)
                    actual_delay = delay * jitter
                    
                    log.warning(f"Server error (attempt {attempt}): {e}. Retrying in {actual_delay:.1f}s")
                    await asyncio.sleep(actual_delay)
                    continue
                else:
                    log.error(f"Non-retryable RPC error: {e}")
                    raise
                    
            except Exception as e:
                log.error(f"Unexpected error in download: {e}")
                raise

    def disconnect(self) -> Awaitable[None]:
        return self.sender.disconnect()


class ParallelDownloader:
    client: TelegramClient
    loop: asyncio.AbstractEventLoop
    dc_id: int
    senders: Optional[List[DownloadSender]]
    auth_key: AuthKey
    network_monitor: Optional['NetworkMonitor']
    allow_mobile_data: bool
    paused: bool
    pause_callback: Optional[callable]
    resume_callback: Optional[callable]

    def __init__(self, client: TelegramClient, dc_id: Optional[int] = None,
                 allow_mobile_data: bool = False, network_monitor: Optional['NetworkMonitor'] = None) -> None:
        self.client = client
        self.loop = self.client.loop
        self.dc_id = dc_id or self.client.session.dc_id
        self.auth_key = (None if dc_id and self.client.session.dc_id != dc_id
                        else self.client.session.auth_key)
        self.senders = None
        self.network_monitor = network_monitor
        self.allow_mobile_data = allow_mobile_data
        self.paused = False
        self.pause_callback = None
        self.resume_callback = None

    async def _cleanup(self) -> None:
        if self.senders:
            await asyncio.gather(*[sender.disconnect() for sender in self.senders])
        self.senders = None

    @staticmethod
    def _get_connection_count(file_size: int, max_count: int = 8,
                             full_size: int = 100 * 1024 * 1024) -> int:
        """Get optimal connection count based on file size.
        
        Args:
            file_size: Size of file in bytes
            max_count: Maximum connections (reduced from 20 to 8 to avoid rate limits)
            full_size: File size threshold for max connections
        """
        if file_size > full_size:
            return max_count
        return max(1, math.ceil((file_size / full_size) * max_count))
    
    async def _check_network_permission(self):
        """Check if current network connection is allowed for downloads"""
        if not NETWORK_MONITOR_AVAILABLE or not self.network_monitor:
            return  # No network monitoring available, allow all connections
        
        if self.allow_mobile_data:
            return  # Mobile data allowed, no restrictions
        
        # Check current connection type
        connection_type = self.network_monitor.detect_connection_type()
        
        if connection_type == NetworkType.MOBILE:
            log.warning("Mobile data detected, pausing download")
            if not self.paused and self.pause_callback:
                self.pause_callback("Download paused: Mobile data detected")
            
            self.paused = True
            
            # Wait for WiFi connection
            log.info("Waiting for WiFi connection...")
            await self.network_monitor.wait_for_wifi()
            
            # Resume download
            self.paused = False
            log.info("WiFi detected, resuming download")
            if self.resume_callback:
                self.resume_callback("Download resumed: WiFi connection established")
        
        elif connection_type == NetworkType.NONE:
            log.warning("No network connection detected")
            if not self.paused and self.pause_callback:
                self.pause_callback("Download paused: No network connection")
            
            self.paused = True
            
            # Wait for any connection
            while self.network_monitor.detect_connection_type() == NetworkType.NONE:
                log.info("Waiting for network connection...")
                await asyncio.sleep(2)
            
            # Check again for WiFi vs mobile after connection is restored
            await self._check_network_permission()
    
    def pause_download(self, reason: str = "Manual pause"):
        """Manually pause the download"""
        self.paused = True
        log.info(f"Download paused: {reason}")
        if self.pause_callback:
            self.pause_callback(reason)
    
    def resume_download(self, reason: str = "Manual resume"):
        """Manually resume the download"""
        self.paused = False
        log.info(f"Download resumed: {reason}")
        if self.resume_callback:
            self.resume_callback(reason)

    async def _init_download(self, connections: int, file: TypeLocation, part_count: int,
                           part_size: int) -> None:
        minimum, remainder = divmod(part_count, connections)

        def get_part_count() -> int:
            nonlocal remainder
            if remainder > 0:
                remainder -= 1
                return minimum + 1
            return minimum

        # Create download senders
        self.senders = [
            await self._create_download_sender(file, 0, part_size, connections * part_size,
                                             get_part_count()),
            *await asyncio.gather(
                *[self._create_download_sender(file, i, part_size, connections * part_size,
                                             get_part_count())
                  for i in range(1, connections)])
        ]

    async def _create_download_sender(self, file: TypeLocation, index: int, part_size: int,
                                    stride: int, part_count: int) -> DownloadSender:
        return DownloadSender(self.client, await self._create_sender(), file, 
                            index * part_size, part_size, stride, part_count)

    async def _create_sender(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        await sender.connect(self.client._connection(dc.ip_address, dc.port, dc.id,
                                                   loggers=self.client._log,
                                                   proxy=self.client._proxy))
        if not self.auth_key:
            log.debug(f"Exporting auth to DC {self.dc_id}")
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(id=auth.id,
                                                                        bytes=auth.bytes)
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key
        return sender

    async def download(self, file: TypeLocation, file_size: int,
                      part_size_kb: Optional[float] = None,
                      connection_count: Optional[int] = None,
                      progress_callback=None,
                      pause_callback=None,
                      resume_callback=None) -> bytes:
        """Download file using parallel connections.
        
        Args:
            file: File location to download
            file_size: Size of file in bytes
            part_size_kb: Part size in KB (default: auto-calculated)
            connection_count: Number of connections (default: auto-calculated)
            progress_callback: Function called with (downloaded_bytes, total_bytes)
        
        Returns:
            Complete file data as bytes
        """
        # Store callbacks
        self.pause_callback = pause_callback
        self.resume_callback = resume_callback
        
        connection_count = connection_count or self._get_connection_count(file_size)
        part_size = int((part_size_kb or utils.get_appropriated_part_size(file_size)) * 1024)
        part_count = math.ceil(file_size / part_size)
        
        log.info(f"Starting parallel download: {connection_count} connections, "
                f"part_size={part_size}, part_count={part_count}")
        
        # Check network connection before starting
        await self._check_network_permission()
        
        await self._init_download(connection_count, file, part_count, part_size)

        # Download all parts
        downloaded_parts = []
        downloaded_bytes = 0
        part = 0
        
        while part < part_count:
            # Check network permission before each batch of downloads
            await self._check_network_permission()
            
            # Wait if paused
            while self.paused:
                log.info("Download paused, waiting for resume...")
                await asyncio.sleep(1)
            
            tasks = []
            for sender in self.senders:
                tasks.append(self.loop.create_task(sender.next()))
            
            # Use asyncio.gather with return_exceptions to handle individual failures
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        log.error(f"Sender {i} failed: {result}")
                        # Don't add failed result, let retry handle it
                        continue
                    
                    data = result
                    if not data:
                        break
                    
                    downloaded_parts.append(data)
                    downloaded_bytes += len(data)
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(downloaded_bytes, file_size)
                    
                    part += 1
                    log.debug(f"Part {part}/{part_count} downloaded ({len(data)} bytes)")
                    
            except Exception as e:
                log.error(f"Batch download error: {e}")
                # Continue to next batch, individual senders will retry

        log.debug("Parallel download finished, cleaning up connections")
        await self._cleanup()

        # Combine all parts
        return b''.join(downloaded_parts)


async def fast_download_file(client: TelegramClient, document: Document, 
                           progress_callback=None, max_connections: int = 8,
                           wifi_only: bool = True, pause_callback=None,
                           resume_callback=None) -> bytes:
    """Fast parallel download of a Telegram file.
    
    Args:
        client: Telethon client
        document: Document to download
        progress_callback: Function called with (downloaded_bytes, total_bytes)
        max_connections: Maximum number of parallel connections
        wifi_only: Only download when connected to WiFi (not mobile data)
        pause_callback: Function called when download is paused
        resume_callback: Function called when download is resumed
    
    Returns:
        Complete file data as bytes
    """
    file_size = document.size
    dc_id, location = utils.get_input_location(document)
    
    # Initialize network monitor if WiFi-only mode is requested
    network_monitor = None
    if wifi_only and NETWORK_MONITOR_AVAILABLE:
        try:
            network_monitor = NetworkMonitor()
            log.info("Network monitoring enabled for WiFi-only downloads")
        except Exception as e:
            log.warning(f"Failed to initialize network monitor: {e}")
            network_monitor = None
    
    # Use parallel downloader
    downloader = ParallelDownloader(
        client, 
        dc_id,
        allow_mobile_data=not wifi_only,
        network_monitor=network_monitor
    )
    
    try:
        data = await downloader.download(
            location, 
            file_size,
            connection_count=min(max_connections, downloader._get_connection_count(file_size)),
            progress_callback=progress_callback,
            pause_callback=pause_callback,
            resume_callback=resume_callback
        )
        return data
    except Exception as e:
        log.error(f"Fast download failed: {e}")
        # Cleanup on error
        try:
            await downloader._cleanup()
        except:
            pass
        raise


async def fast_download_to_file(client: TelegramClient, document: Document, 
                               file_path: str, progress_callback=None, 
                               max_connections: int = 8, wifi_only: bool = True,
                               pause_callback=None, resume_callback=None) -> None:
    """Fast parallel download of a Telegram file to disk.
    
    Args:
        client: Telethon client
        document: Document to download
        file_path: Path to save the file
        progress_callback: Function called with (downloaded_bytes, total_bytes)
        max_connections: Maximum number of parallel connections
        wifi_only: Only download when connected to WiFi (not mobile data)
        pause_callback: Function called when download is paused
        resume_callback: Function called when download is resumed
    """
    # Download to memory first, then write to file
    # This is simpler than coordinating parallel writes to disk
    data = await fast_download_file(
        client, document, progress_callback, max_connections, 
        wifi_only, pause_callback, resume_callback
    )
    
    # Write to file
    with open(file_path, 'wb') as f:
        f.write(data)
    
    log.info(f"Fast download completed: {file_path} ({len(data)} bytes)")


# Convenience function for WiFi-only downloads
async def fast_download_wifi_only(client: TelegramClient, document: Document,
                                 progress_callback=None, max_connections: int = 8,
                                 pause_callback=None, resume_callback=None) -> bytes:
    """Convenience function for WiFi-only downloads with network monitoring"""
    return await fast_download_file(
        client=client,
        document=document,
        progress_callback=progress_callback,
        max_connections=max_connections,
        wifi_only=True,
        pause_callback=pause_callback,
        resume_callback=resume_callback
    )