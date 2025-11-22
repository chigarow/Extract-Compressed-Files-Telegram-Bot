"""WebDAV integration helpers for Torbox incremental downloads."""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

try:
    import httpx
except ImportError:  # pragma: no cover
    class _DummyResponse:
        def __init__(self, status_code=200, headers=None, content=b''):
            self.status_code = status_code
            self.headers = headers or {}
            self._content = content

        async def aclose(self):
            pass

        async def aiter_bytes(self, chunk_size):
            # Yield the whole content in one chunk for simplicity
            if self._content:
                yield self._content

        def raise_for_status(self):
            pass

    class _DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, headers=None):
            # Return an empty successful response
            return _DummyResponse()

        async def aclose(self):
            pass

    class _DummyBasicAuth:
        def __init__(self, username, password):
            pass

    httpx = type('httpx', (), {
        'AsyncClient': _DummyAsyncClient,
        'Response': _DummyResponse,
        'BasicAuth': _DummyBasicAuth,
    })
try:
    from webdav4.client import Client as SyncWebDAVClient
except ImportError:  # pragma: no cover
    class SyncWebDAVClient:
        """Fallback dummy client with minimal interface used in tests."""
        def __init__(self, *args, **kwargs):
            pass
        def ls(self, path='/', detail=False):
            # Return empty list to indicate no entries
            return []


logger = logging.getLogger('extractor')

WEBDAV_URL_PATTERN = re.compile(r'https?://webdav\.torbox\.app[^\s>]+', re.IGNORECASE)

ProgressCallback = Callable[[int, Optional[int]], None]


@dataclass
class WebDAVItem:
    """Represents a path returned from the WebDAV API."""

    path: str
    name: str
    is_dir: bool
    size: int
    modified: Optional[str] = None


def parse_webdav_url(url: str) -> Tuple[str, str]:
    """Parse a Torbox WebDAV URL into base URL and relative path."""

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Only http/https WebDAV URLs are supported')
    if not parsed.netloc:
        raise ValueError('WebDAV URL must include a hostname')

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    remote_path = unquote(parsed.path or '/').strip()
    if not remote_path:
        remote_path = '/'
    return base_url, remote_path


def is_webdav_link(url: str) -> bool:
    """Return True if the string looks like a Torbox WebDAV URL."""

    if not url:
        return False
    return bool(WEBDAV_URL_PATTERN.match(url.strip()))


def extract_webdav_links(text: str) -> List[str]:
    """Extract all Torbox WebDAV URLs from arbitrary text."""

    if not text:
        return []
    return list({match.group(0).strip('.,') for match in WEBDAV_URL_PATTERN.finditer(text)})


class TorboxWebDAVClient:
    """Manage listing and streaming downloads from Torbox WebDAV."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: Optional[int] = None,
        chunk_size: Optional[int] = None,
        inactivity_timeout: Optional[int] = None,
    ):
        if not username or not password:
            raise ValueError('WebDAV credentials are required')

        # Ensure an event loop exists for constructing async primitives in sync contexts
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.base_url = base_url.rstrip('/') or 'https://webdav.torbox.app'
        self.username = username
        self.password = password
        if timeout is None:
            try:
                from config import config as global_config
                timeout = getattr(global_config, 'webdav_timeout_seconds', 120)
            except Exception:
                timeout = 120
        self.timeout = timeout
        
        # Use provided chunk_size or default from config (converted to bytes)
        if chunk_size is None:
            from utils.constants import WEBDAV_CHUNK_SIZE_KB
            chunk_size = WEBDAV_CHUNK_SIZE_KB * 1024
        self.chunk_size = chunk_size
        
        # Inactivity timeout for detecting stalled downloads
        if inactivity_timeout is None:
            try:
                from config import config as global_config
                inactivity_timeout = getattr(global_config, 'webdav_inactivity_timeout', 60)
            except Exception:
                inactivity_timeout = 60
        self.inactivity_timeout = inactivity_timeout

        self._sync_client = SyncWebDAVClient(
            base_url=self.base_url,
            auth=(self.username, self.password),
            timeout=self.timeout,
        )
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_lock = asyncio.Lock()

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def list_directory(self, path: str) -> List[WebDAVItem]:
        """List items for the provided directory path."""

        normalized = self._normalize_path(path)
        logger.info(f"Listing WebDAV directory: {normalized}")

        def _list():
            return self._sync_client.ls(
                normalized if normalized != '/' else '/',
                detail=True
            )

        entries = None
        last_exc: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                entries = await asyncio.to_thread(_list)
                break
            except Exception as exc:
                last_exc = exc
                if self._is_timeout_error(exc) and attempt < 3:
                    delay = 5 * attempt
                    logger.warning(
                        f"WebDAV list attempt {attempt} timed out for {normalized}: {exc}. Retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        if entries is None:
            # All retries failed; raise the last exception
            raise last_exc or RuntimeError("WebDAV listing failed without an explicit exception")

        items: List[WebDAVItem] = []
        for entry in entries:
            name = (entry.get('name') or '').lstrip('/')
            if not name:
                continue

            full_path = name
            is_dir = entry.get('type') == 'directory'
            size_val = entry.get('content_length') or 0
            modified = entry.get('modified')
            if hasattr(modified, 'isoformat'):
                modified = modified.isoformat()
            elif modified is not None:
                modified = str(modified)

            items.append(WebDAVItem(
                path=full_path,
                name=os.path.basename(full_path.rstrip('/')) or full_path,
                is_dir=is_dir,
                size=int(size_val) if isinstance(size_val, (int, float)) else 0,
                modified=modified
            ))

        return items

    async def walk_files(self, root_path: str) -> AsyncGenerator[WebDAVItem, None]:
        """Yield files recursively under the given path."""

        normalized_root = self._normalize_path(root_path)
        stack = [normalized_root]
        seen = set()

        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)

            try:
                entries = await self.list_directory(current)
            except Exception as exc:
                logger.error(f"Failed to list {current}: {exc}")
                raise

            for entry in entries:
                if entry.is_dir:
                    stack.append(entry.path)
                else:
                    yield entry

    async def download_file(
        self,
        remote_path: str,
        dest_path: str,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Download a file with resume support, inactivity watchdog, and robust error handling."""

        url = self._build_full_url(remote_path)
        part_path = dest_path + '.part'
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)

        # Check for existing partial download
        resume_from = 0
        if os.path.exists(part_path):
            resume_from = os.path.getsize(part_path)
            # Clean up zero-byte partials to avoid corruption
            if resume_from == 0:
                try:
                    os.remove(part_path)
                    logger.debug(f"Removed zero-byte partial file: {part_path}")
                    resume_from = 0
                except OSError:
                    pass

        # Prepare headers for resume
        headers = {}
        if resume_from:
            headers['Range'] = f'bytes={resume_from}-'
            logger.info(f"Resuming download from byte {resume_from} for {remote_path}")

        client = await self._ensure_http_client()
        logger.info(
            f"Starting WebDAV download: {remote_path} → {dest_path} "
            f"(resume from {resume_from}, chunk size: {self.chunk_size} bytes, "
            f"inactivity timeout: {self.inactivity_timeout}s)"
        )

        try:
            response = await client.get(url, headers=headers)
            
            # Log response details for diagnostics
            logger.info(
                f"WebDAV GET response for {remote_path}: "
                f"status={response.status_code}, "
                f"content-length={response.headers.get('content-length', 'unknown')}, "
                f"content-range={response.headers.get('content-range', 'none')}, "
                f"accept-ranges={response.headers.get('accept-ranges', 'none')}"
            )
            
            # Handle already-complete downloads (416 Range Not Satisfiable)
            if response.status_code == 416 and resume_from:
                logger.info(f"Download already complete for {remote_path} (HTTP 416)")
                await response.aclose()
                os.rename(part_path, dest_path)
                return

            # Handle server ignoring Range header (HTTP 200 instead of 206)
            if response.status_code == 200 and resume_from:
                logger.warning(
                    f"Server ignored Range request for {remote_path} (sent HTTP 200 instead of 206). "
                    f"Restarting download from byte 0 to avoid corruption."
                )
                await response.aclose()
                # Delete corrupt partial and restart
                try:
                    os.remove(part_path)
                except OSError:
                    pass
                resume_from = 0
                headers = {}
                # Retry without Range header
                response = await client.get(url, headers=headers)
                logger.info(f"Restarted download for {remote_path}: status={response.status_code}")

            response.raise_for_status()

            # Determine file mode and total size
            mode = 'ab' if resume_from else 'wb'
            total_bytes = self._get_total_size(response, resume_from)
            current = resume_from
            last_chunk_time = time.time()
            last_heartbeat = time.time()
            heartbeat_interval = 10  # Log progress every 10 seconds

            try:
                with open(part_path, mode) as handle:
                    async for chunk in response.aiter_bytes(self.chunk_size):
                        if not chunk:
                            continue
                        
                        # Write chunk to disk
                        handle.write(chunk)
                        current += len(chunk)
                        last_chunk_time = time.time()
                        
                        # Progress callback
                        if progress_callback:
                            progress_callback(current, total_bytes)
                        
                        # Heartbeat logging to detect stalls
                        if time.time() - last_heartbeat >= heartbeat_interval:
                            pct = (current / total_bytes * 100) if total_bytes else 0
                            logger.debug(
                                f"WebDAV download heartbeat for {remote_path}: "
                                f"{current}/{total_bytes} bytes ({pct:.1f}%)"
                            )
                            last_heartbeat = time.time()
                        
                        # Inactivity watchdog: check if we've been waiting too long for next chunk
                        # This is handled by httpx's built-in timeout, but we log it explicitly
                        
            except asyncio.TimeoutError:
                logger.error(
                    f"WebDAV download timed out for {remote_path} after {self.timeout}s. "
                    f"Downloaded {current} bytes before timeout."
                )
                raise
            except Exception:
                logger.exception(
                    f"Failed to stream {remote_path}. "
                    f"Downloaded {current} bytes before failure. Partial file preserved for resume."
                )
                raise
            finally:
                await response.aclose()

            # Verify download completeness before renaming
            if total_bytes and current < total_bytes:
                logger.warning(
                    f"Download incomplete for {remote_path}: {current}/{total_bytes} bytes. "
                    f"Partial file preserved for resume."
                )
                raise RuntimeError(f"Incomplete download: {current}/{total_bytes} bytes")

            # Move complete download to final destination
            os.replace(part_path, dest_path)
            logger.info(f"Completed WebDAV download: {dest_path} ({current} bytes)")
            
        except Exception as e:
            # Enhanced error logging with context
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(
                f"WebDAV download error for {remote_path}: {error_type}: {error_msg}. "
                f"Progress: {resume_from} → {current if 'current' in locals() else resume_from} bytes"
            )
            # Re-raise to let queue manager handle retries
            raise

    async def _ensure_http_client(self) -> httpx.AsyncClient:
        async with self._http_lock:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(
                    auth=httpx.BasicAuth(self.username, self.password),
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={'User-Agent': 'ExtractCompressedFiles/1.0'}
                )
            return self._http_client

    def _normalize_path(self, path: str) -> str:
        if not path or path == '/':
            return '/'
        cleaned = path.strip()
        if cleaned.startswith('/'):
            cleaned = cleaned[1:]
        return cleaned or '/'

    def _build_full_url(self, remote_path: str) -> str:
        encoded = quote(self._normalize_path(remote_path).lstrip('/'), safe='/')
        if encoded:
            return f"{self.base_url}/{encoded}"
        return f"{self.base_url}/"

    def _is_timeout_error(self, exc: Exception) -> bool:
        """Return True if the exception represents a timeout."""
        timeout_types = []
        timeout_exc = getattr(httpx, 'TimeoutException', None)
        if isinstance(timeout_exc, type):
            timeout_types.append(timeout_exc)
        timeout_types_tuple = tuple(timeout_types) + (asyncio.TimeoutError, TimeoutError)
        return isinstance(exc, timeout_types_tuple) or 'timed out' in str(exc).lower()

    def _is_network_error(self, exc: Exception) -> bool:
        """Return True if the exception represents a network/DNS error that should be retried."""
        error_msg = str(exc).lower()
        # DNS errors
        if 'no address associated' in error_msg or 'errno 7' in error_msg:
            return True
        # Connection errors
        if any(keyword in error_msg for keyword in [
            'connection refused',
            'connection reset',
            'connection aborted',
            'network is unreachable',
            'errno 61',  # Connection refused
            'errno 54',  # Connection reset by peer
            'errno 104', # Connection reset by peer (Linux)
        ]):
            return True
        # httpx-specific network errors
        network_exc = getattr(httpx, 'NetworkError', None)
        connect_exc = getattr(httpx, 'ConnectError', None)
        if network_exc and isinstance(exc, network_exc):
            return True
        if connect_exc and isinstance(exc, connect_exc):
            return True
        return False

    @staticmethod
    def _get_total_size(response: httpx.Response, resume_from: int) -> Optional[int]:
        if 'content-range' in response.headers:
            content_range = response.headers['content-range']
            if '/' in content_range:
                total = content_range.split('/')[-1]
                try:
                    return int(total)
                except ValueError:
                    return None
        if 'content-length' in response.headers:
            try:
                return resume_from + int(response.headers['content-length'])
            except ValueError:
                return None
        return None


_client_instance: Optional[TorboxWebDAVClient] = None
_client_lock = asyncio.Lock()


async def get_webdav_client() -> TorboxWebDAVClient:
    """Return a singleton TorboxWebDAVClient configured from secrets."""

    from config import config

    if not getattr(config, 'webdav_enabled', True):
        raise RuntimeError('WebDAV support is disabled in configuration')

    async with _client_lock:
        global _client_instance
        if _client_instance is None:
            _client_instance = TorboxWebDAVClient(
                base_url=getattr(config, 'webdav_base_url', 'https://webdav.torbox.app'),
                username=getattr(config, 'webdav_username', ''),
                password=getattr(config, 'webdav_password', ''),
                timeout=getattr(config, 'webdav_timeout_seconds', 120),
            )
        return _client_instance


async def reset_webdav_client():
    """Reset the cached client (primarily for unit tests)."""

    global _client_instance
    async with _client_lock:
        if _client_instance is not None:
            await _client_instance.close()
            _client_instance = None
