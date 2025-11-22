"""WebDAV integration helpers for Torbox incremental downloads."""

import asyncio
import logging
import os
import re
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
        """Download a file with resume support via HTTP range requests."""

        url = self._build_full_url(remote_path)
        part_path = dest_path + '.part'
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)

        resume_from = 0
        if os.path.exists(part_path):
            resume_from = os.path.getsize(part_path)

        headers = {}
        if resume_from:
            headers['Range'] = f'bytes={resume_from}-'

        client = await self._ensure_http_client()
        logger.info(f"Downloading WebDAV file {remote_path} → {dest_path} (resume from {resume_from})")

        response = await client.get(url, headers=headers)
        if response.status_code == 416 and resume_from:
            # Already downloaded fully
            os.rename(part_path, dest_path)
            return

        if response.status_code == 200 and resume_from:
            logger.warning(
                f"Server ignored range request for {remote_path}; restarting download"
            )
            resume_from = 0

        response.raise_for_status()

        mode = 'ab' if resume_from else 'wb'
        total_bytes = self._get_total_size(response, resume_from)
        current = resume_from

        try:
            with open(part_path, mode) as handle:
                async for chunk in response.aiter_bytes(self.chunk_size):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    current += len(chunk)
                    if progress_callback:
                        progress_callback(current, total_bytes)
        except Exception:
            logger.exception(f"Failed to stream {remote_path}")
            raise
        finally:
            await response.aclose()

        os.replace(part_path, dest_path)
        logger.info(f"Completed WebDAV download: {dest_path}")

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
