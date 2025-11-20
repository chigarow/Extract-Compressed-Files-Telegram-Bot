"""Tests for WebDAV integration (link detection, queue tasks, and downloads)."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from utils.queue_manager import QueueManager
from utils.webdav_client import WebDAVItem, extract_webdav_links, parse_webdav_url


class DummyEvent:
    """Simple event-like object capturing replies."""

    def __init__(self):
        self.messages = []

    async def reply(self, text):
        self.messages.append(text)
        return SimpleNamespace(id=1, peer_id=None)


class StubWebDAVClient:
    """Stubbed WebDAV client for tests."""

    def __init__(self, items=None):
        self.items = items or []
        self.downloads = []

    async def walk_files(self, root_path):
        for item in self.items:
            yield item

    async def download_file(self, remote_path, dest_path, progress_callback=None):
        self.downloads.append(remote_path)
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
        with open(dest_path, 'wb') as handle:
            handle.write(b'dummy')
        if progress_callback:
            progress_callback(len(b'dummy'), len(b'dummy'))


@pytest.fixture
def queue_manager(tmp_path, monkeypatch):
    """QueueManager configured to use temporary persistence files."""

    download_file = tmp_path / 'download_queue.json'
    upload_file = tmp_path / 'upload_queue.json'
    retry_file = tmp_path / 'retry_queue.json'
    webdav_dir = tmp_path / 'webdav'
    webdav_dir.mkdir()

    monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(download_file))
    monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(upload_file))
    monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(retry_file))
    monkeypatch.setattr('utils.queue_manager.WEBDAV_DIR', str(webdav_dir))

    manager = QueueManager()
    manager._test_webdav_dir = str(webdav_dir)
    return manager


@pytest.mark.asyncio
async def test_webdav_walk_enqueues_download_tasks(queue_manager, monkeypatch):
    """Crawling a WebDAV path should enqueue file download tasks with sanitized paths."""

    items = [
        WebDAVItem(path='Milacat/Photo One.jpg', name='Milacat/Photo One.jpg', is_dir=False, size=1024),
        WebDAVItem(path='Milacat/SubFolder/Clip.mp4', name='Milacat/SubFolder/Clip.mp4', is_dir=False, size=2048)
    ]
    stub_client = StubWebDAVClient(items)
    monkeypatch.setattr('utils.webdav_client.get_webdav_client', AsyncMock(return_value=stub_client))

    event = DummyEvent()
    task = {
        'type': 'webdav_walk_download',
        'remote_path': '/Milacat',
        'display_name': 'Milacat',
        'filename': 'WebDAV: Milacat',
        'event': event
    }

    await queue_manager._execute_webdav_walk_task(task)

    assert queue_manager.download_queue.qsize() == 2
    queued = [queue_manager.download_queue.get_nowait() for _ in range(queue_manager.download_queue.qsize())]
    assert all(item['type'] == 'webdav_file_download' for item in queued)
    assert queued[0]['temp_path'].endswith(os.path.join('Milacat', 'Photo_One.jpg'))
    assert queued[1]['temp_path'].endswith(os.path.join('Milacat', 'SubFolder', 'Clip.mp4'))
    # Ensure user notified about discovered files
    assert event.messages[-1].startswith('📁 Queued 2 files')


@pytest.mark.asyncio
async def test_webdav_file_download_media_enqueue(queue_manager, monkeypatch):
    """WebDAV media files should be downloaded and enqueued for media upload."""

    stub_client = StubWebDAVClient()
    monkeypatch.setattr('utils.webdav_client.get_webdav_client', AsyncMock(return_value=stub_client))

    webdav_dir = getattr(queue_manager, '_test_webdav_dir')
    media_task = {
        'type': 'webdav_file_download',
        'remote_path': 'cats/video.mp4',
        'temp_path': os.path.join(webdav_dir, 'cats', 'video.mp4'),
        'filename': 'video.mp4',
        'display_name': 'cats'
    }

    queue_manager.add_upload_task = AsyncMock()

    await queue_manager._execute_webdav_file_task(media_task)

    queue_manager.add_upload_task.assert_awaited_once()
    queued_task = queue_manager.add_upload_task.await_args.args[0]
    assert queued_task['type'] == 'webdav_media_upload'
    assert queued_task['filename'] == 'video.mp4'


@pytest.mark.asyncio
async def test_webdav_file_download_document_enqueue(queue_manager, monkeypatch):
    """Non-media WebDAV files should be enqueued directly for upload."""

    stub_client = StubWebDAVClient()
    monkeypatch.setattr('utils.webdav_client.get_webdav_client', AsyncMock(return_value=stub_client))

    webdav_dir = getattr(queue_manager, '_test_webdav_dir')
    doc_path = os.path.join(webdav_dir, 'cats', 'notes.txt')
    doc_task = {
        'type': 'webdav_file_download',
        'remote_path': 'cats/notes.txt',
        'temp_path': doc_path,
        'filename': 'notes.txt',
        'display_name': 'cats'
    }

    queue_manager.add_upload_task = AsyncMock()

    await queue_manager._execute_webdav_file_task(doc_task)

    queue_manager.add_upload_task.assert_awaited_once()
    queued_task = queue_manager.add_upload_task.await_args.args[0]
    assert queued_task['type'] == 'webdav_document_upload'


@pytest.mark.asyncio
async def test_webdav_media_upload_task_execution(queue_manager, monkeypatch):
    """A WebDAV media upload task should result in a call to upload_media_file."""
    
    mock_telegram_ops = AsyncMock()
    mock_telegram_ops.upload_media_file = AsyncMock()

    monkeypatch.setattr('utils.queue_manager.TelegramOperations', lambda client: mock_telegram_ops)
    monkeypatch.setattr('utils.queue_manager.get_client', AsyncMock())
    monkeypatch.setattr('utils.queue_manager.ensure_target_entity', AsyncMock())
    monkeypatch.setattr('utils.queue_manager.CacheManager', AsyncMock())
    monkeypatch.setattr('utils.media_processing.needs_video_processing', lambda x: False)

    webdav_dir = getattr(queue_manager, '_test_webdav_dir')
    media_path = os.path.join(webdav_dir, 'video.mp4')
    with open(media_path, 'wb') as f:
        f.write(b'some video data')

    upload_task = {
        'type': 'webdav_media_upload',
        'file_path': media_path,
        'filename': 'video.mp4',
        'event': None
    }

    await queue_manager._execute_upload_task(upload_task)

    mock_telegram_ops.upload_media_file.assert_awaited_once()
    
    args, kwargs = mock_telegram_ops.upload_media_file.await_args
    assert args[1] == media_path
    assert 'video.mp4' in kwargs['caption']


def test_webdav_link_detection_and_parsing():
    """WebDAV link helpers should detect deduplicated URLs and decode paths."""

    text = (
        "Mirror folder: https://webdav.torbox.app/mila%20cat/Photos/\n"
        "Duplicate https://webdav.torbox.app/mila%20cat/Photos/"
    )
    links = extract_webdav_links(text)
    assert len(links) == 1
    base_url, remote_path = parse_webdav_url(links[0])
    assert base_url == 'https://webdav.torbox.app'
    assert remote_path == '/mila cat/Photos/'