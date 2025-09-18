# FastTelethon parallel download implementation
# Based on https://gist.github.com/painor/7e74de80ae0c819d3e9abcf9989a8dd6
# Adapted for our extract-compressed-files.py use case

import asyncio
import logging
import math
import os
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
        result = await self.client._call(self.sender, self.request)
        self.remaining -= 1
        self.request.offset += self.stride
        return result.bytes

    def disconnect(self) -> Awaitable[None]:
        return self.sender.disconnect()


class ParallelDownloader:
    client: TelegramClient
    loop: asyncio.AbstractEventLoop
    dc_id: int
    senders: Optional[List[DownloadSender]]
    auth_key: AuthKey

    def __init__(self, client: TelegramClient, dc_id: Optional[int] = None) -> None:
        self.client = client
        self.loop = self.client.loop
        self.dc_id = dc_id or self.client.session.dc_id
        self.auth_key = (None if dc_id and self.client.session.dc_id != dc_id
                        else self.client.session.auth_key)
        self.senders = None

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
                      progress_callback=None) -> bytes:
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
        connection_count = connection_count or self._get_connection_count(file_size)
        part_size = int((part_size_kb or utils.get_appropriated_part_size(file_size)) * 1024)
        part_count = math.ceil(file_size / part_size)
        
        log.info(f"Starting parallel download: {connection_count} connections, "
                f"part_size={part_size}, part_count={part_count}")
        
        await self._init_download(connection_count, file, part_count, part_size)

        # Download all parts
        downloaded_parts = []
        downloaded_bytes = 0
        part = 0
        
        while part < part_count:
            tasks = []
            for sender in self.senders:
                tasks.append(self.loop.create_task(sender.next()))
            
            for task in tasks:
                data = await task
                if not data:
                    break
                downloaded_parts.append(data)
                downloaded_bytes += len(data)
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(downloaded_bytes, file_size)
                
                part += 1
                log.debug(f"Part {part}/{part_count} downloaded ({len(data)} bytes)")

        log.debug("Parallel download finished, cleaning up connections")
        await self._cleanup()

        # Combine all parts
        return b''.join(downloaded_parts)


async def fast_download_file(client: TelegramClient, document: Document, 
                           progress_callback=None, max_connections: int = 8) -> bytes:
    """Fast parallel download of a Telegram file.
    
    Args:
        client: Telethon client
        document: Document to download
        progress_callback: Function called with (downloaded_bytes, total_bytes)
        max_connections: Maximum number of parallel connections
    
    Returns:
        Complete file data as bytes
    """
    file_size = document.size
    dc_id, location = utils.get_input_location(document)
    
    # Use parallel downloader
    downloader = ParallelDownloader(client, dc_id)
    
    try:
        data = await downloader.download(
            location, 
            file_size,
            connection_count=min(max_connections, downloader._get_connection_count(file_size)),
            progress_callback=progress_callback
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
                               max_connections: int = 8) -> None:
    """Fast parallel download of a Telegram file to disk.
    
    Args:
        client: Telethon client
        document: Document to download
        file_path: Path to save the file
        progress_callback: Function called with (downloaded_bytes, total_bytes)
        max_connections: Maximum number of parallel connections
    """
    # Download to memory first, then write to file
    # This is simpler than coordinating parallel writes to disk
    data = await fast_download_file(client, document, progress_callback, max_connections)
    
    # Write to file
    with open(file_path, 'wb') as f:
        f.write(data)
    
    log.info(f"Fast download completed: {file_path} ({len(data)} bytes)")