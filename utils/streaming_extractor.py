"""Streaming archive extraction helpers for low-storage environments."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import AsyncGenerator, Iterable, List, Optional

logger = logging.getLogger('extractor')


@dataclass
class StreamingEntry:
    """Represents a single extracted archive entry stored temporarily on disk."""

    entry_name: str
    temp_path: str
    display_name: str
    size_bytes: int
    media_type: str  # 'images', 'videos', or 'media'


class StreamingManifest:
    """Persists streaming extraction progress for crash recovery."""

    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        self.processed: set[str] = set()
        self.total_files: int = 0
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.manifest_path):
            return
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.processed = set(data.get('processed', []))
            self.total_files = data.get('total_files', 0)
        except Exception as exc:
            logger.warning(f"Failed to load streaming manifest {self.manifest_path}: {exc}")
            self.processed = set()
            self.total_files = 0

    def mark_completed(self, entries: Iterable[str]) -> None:
        self.processed.update(entries)
        self._save()

    def set_total_files(self, total: int) -> None:
        if self.total_files != total:
            self.total_files = total
            self._save()

    def _save(self) -> None:
        try:
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {'total_files': self.total_files, 'processed': sorted(self.processed)}, f, indent=2
                )
        except Exception as exc:
            logger.warning(f"Failed to save streaming manifest {self.manifest_path}: {exc}")

    def delete(self) -> None:
        try:
            if os.path.exists(self.manifest_path):
                os.remove(self.manifest_path)
        except OSError as exc:
            logger.warning(f"Failed to delete manifest {self.manifest_path}: {exc}")


class StreamingExtractor:
    """Streams archive entries sequentially to minimize disk usage."""

    def __init__(
        self,
        archive_path: str,
        temp_dir: str,
        media_extensions: set,
        photo_extensions: set,
        video_extensions: set,
        manifest_dir: str,
        min_free_bytes: int,
        check_interval: int = 30
    ):
        self.archive_path = archive_path
        self.temp_dir = temp_dir
        self.media_extensions = media_extensions
        self.photo_ext = photo_extensions
        self.video_ext = video_extensions
        safe_name = os.path.basename(archive_path).replace(os.sep, '_')
        self.manifest = StreamingManifest(os.path.join(manifest_dir, f"{safe_name}.json"))
        self.manifest_path = self.manifest.manifest_path
        self.min_free_bytes = max(min_free_bytes, 0)
        self.check_interval = check_interval
        self.low_space_notified = False
        os.makedirs(self.temp_dir, exist_ok=True)

    async def stream_entries(self, event=None) -> AsyncGenerator[StreamingEntry, None]:
        """Yield StreamingEntry objects one at a time."""
        archive_lower = self.archive_path.lower()
        if archive_lower.endswith('.zip'):
            async for entry in self._stream_zip_entries(event):
                yield entry
        else:
            raise RuntimeError('Streaming extraction currently supports ZIP archives only')

    def get_total_media_files(self) -> int:
        """Counts the total number of media files in the archive without extracting."""
        archive_lower = self.archive_path.lower()
        if not archive_lower.endswith('.zip'):
            return 0
        
        import zipfile
        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zip_ref:
                return sum(
                    1
                    for info in zip_ref.infolist()
                    if not info.is_dir() and os.path.splitext(info.filename)[1].lower() in self.media_extensions
                )
        except zipfile.BadZipFile:
            return 0

    def get_total_files_by_type(self, media_type: str) -> int:
        """Counts the total number of files of a specific media type in the archive."""
        archive_lower = self.archive_path.lower()
        if not archive_lower.endswith('.zip'):
            return 0

        extensions = set()
        if media_type == 'images':
            extensions = self.photo_ext
        elif media_type == 'videos':
            extensions = self.video_ext
        else:
            return 0

        import zipfile
        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zip_ref:
                return sum(
                    1
                    for info in zip_ref.infolist()
                    if not info.is_dir() and os.path.splitext(info.filename)[1].lower() in extensions
                )
        except zipfile.BadZipFile:
            return 0

    async def _stream_zip_entries(self, event=None) -> AsyncGenerator[StreamingEntry, None]:
        import zipfile

        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zip_ref:
                entries: List[zipfile.ZipInfo] = zip_ref.infolist()
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f'Invalid ZIP archive: {exc}') from exc

        total_media_files = sum(
            1
            for info in entries
            if not info.is_dir() and os.path.splitext(info.filename)[1].lower() in self.media_extensions
        )
        self.manifest.set_total_files(total_media_files)

        for info in entries:
            if info.is_dir():
                continue
            entry_name = info.filename
            if entry_name in self.manifest.processed:
                continue
            ext = os.path.splitext(entry_name)[1].lower()
            if ext not in self.media_extensions:
                continue

            await self._wait_for_free_space(event)
            temp_path = await asyncio.to_thread(self._extract_zip_entry, entry_name, ext)
            media_type = self._classify_media(ext)
            yield StreamingEntry(
                entry_name=entry_name,
                temp_path=temp_path,
                display_name=os.path.basename(entry_name) or entry_name,
                size_bytes=info.file_size,
                media_type=media_type
            )

    def _extract_zip_entry(self, entry_name: str, ext: str) -> str:
        import zipfile

        os.makedirs(self.temp_dir, exist_ok=True)
        suffix = ext if ext else '.tmp'
        with tempfile.NamedTemporaryFile(delete=False, dir=self.temp_dir, suffix=suffix) as temp_file:
            temp_path = temp_file.name

        with zipfile.ZipFile(self.archive_path, 'r') as zip_ref:
            with zip_ref.open(entry_name) as src, open(temp_path, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)

        return temp_path

    def _classify_media(self, ext: str) -> str:
        if ext in self.photo_ext:
            return 'images'
        if ext in self.video_ext:
            return 'videos'
        return 'media'

    async def _wait_for_free_space(self, event=None) -> None:
        if self.min_free_bytes <= 0:
            return

        while True:
            free_bytes = shutil.disk_usage(self.temp_dir).free
            if free_bytes >= self.min_free_bytes:
                if self.low_space_notified and event:
                    try:
                        await event.reply('✅ Storage space recovered, resuming extraction...')
                    except Exception as exc:
                        logger.warning(f"Could not send storage recovery message: {exc}")
                self.low_space_notified = False
                return

            if not self.low_space_notified and event:
                try:
                    required_gb = self.min_free_bytes / (1024 ** 3)
                    await event.reply(
                        f'⚠️ Low storage detected. Need at least {required_gb:.1f} GB free to continue extraction. '
                        'Pausing until space is freed...'
                    )
                except Exception as exc:
                    logger.warning(f"Could not send low storage warning: {exc}")
                self.low_space_notified = True

            await asyncio.sleep(self.check_interval)

    def mark_entries_completed(self, entries: Iterable[str]) -> None:
        self.manifest.mark_completed(entries)

    def finalize(self) -> None:
        self.manifest.delete()


def mark_streaming_entries_completed(manifest_path: Optional[str], entries: Iterable[str]) -> None:
    """Utility to mark entries as completed from upload workers."""
    if not manifest_path or not entries:
        return
    manifest = StreamingManifest(manifest_path)
    manifest.mark_completed(entries)
