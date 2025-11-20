import asyncio
import contextlib
import json
import os
import zipfile

import pytest
from unittest.mock import AsyncMock, patch

from utils.streaming_extractor import StreamingExtractor
from utils.queue_manager import QueueManager, StreamingBatchBuilder, TELEGRAM_ALBUM_MAX_FILES
from utils.constants import (
    MEDIA_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
)


@pytest.mark.asyncio
async def test_streaming_extractor_yields_entries_and_updates_manifest(tmp_path):
    archive_path = tmp_path / 'test_archive.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('folder/photo1.jpg', 'photo')
        zf.writestr('video1.mp4', 'video')

    extractor = StreamingExtractor(
        archive_path=str(archive_path),
        temp_dir=str(tmp_path / 'temp'),
        media_extensions=set(MEDIA_EXTENSIONS),
        photo_extensions=set(PHOTO_EXTENSIONS),
        video_extensions=set(VIDEO_EXTENSIONS),
        manifest_dir=str(tmp_path / 'manifests'),
        min_free_bytes=0,
        check_interval=1
    )

    entries = []
    async for entry in extractor.stream_entries():
        entries.append(entry)

    assert len(entries) == 2
    for entry in entries:
        assert os.path.exists(entry.temp_path)

    extractor.mark_entries_completed(e.entry_name for e in entries)
    with open(extractor.manifest_path, 'r', encoding='utf-8') as manifest_file:
        data = json.load(manifest_file)
    assert sorted(data['processed']) == sorted(e.entry_name for e in entries)

    extractor.finalize()
    assert not os.path.exists(extractor.manifest_path)


@pytest.mark.asyncio
async def test_grouped_upload_cleans_streaming_files(tmp_path):
    queue_manager = QueueManager()
    file1 = tmp_path / 'file1.jpg'
    file2 = tmp_path / 'file2.jpg'
    file1.write_text('a')
    file2.write_text('b')
    manifest_path = tmp_path / 'manifest.json'
    os.makedirs(manifest_path.parent, exist_ok=True)
    manifest_path.write_text(json.dumps({'processed': []}))

    task = {
        'type': 'grouped_media',
        'media_type': 'images',
        'event': AsyncMock(),
        'file_paths': [str(file1), str(file2)],
        'filename': 'Test Batch',
        'source_archive': 'Test.zip',
        'is_grouped': True,
        'cleanup_file_paths': True,
        'streaming_manifest': str(manifest_path),
        'streaming_entries': ['photo1.jpg', 'photo2.jpg']
    }

    with patch('utils.telegram_operations.TelegramOperations') as mock_ops_class, \
            patch('utils.telegram_operations.ensure_target_entity', AsyncMock(return_value=object())):
        mock_ops = mock_ops_class.return_value
        mock_ops.upload_media_grouped = AsyncMock()
        await queue_manager._execute_grouped_upload(task)

    assert not file1.exists()
    assert not file2.exists()
    data = json.loads(manifest_path.read_text())
    assert sorted(data['processed']) == ['photo1.jpg', 'photo2.jpg']


@pytest.mark.asyncio
async def test_wait_for_free_space_warns_and_recovers(tmp_path, monkeypatch):
    archive_path = tmp_path / 'archive.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('media.jpg', 'content')

    extractor = StreamingExtractor(
        archive_path=str(archive_path),
        temp_dir=str(tmp_path / 'temp'),
        media_extensions=set(MEDIA_EXTENSIONS),
        photo_extensions=set(PHOTO_EXTENSIONS),
        video_extensions=set(VIDEO_EXTENSIONS),
        manifest_dir=str(tmp_path / 'manifest'),
        min_free_bytes=10,
        check_interval=1
    )

    class Usage:
        def __init__(self, free):
            self.free = free

    usage_cycle = iter([Usage(0), Usage(100)])

    def fake_disk_usage(_):
        return next(usage_cycle)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr('shutil.disk_usage', fake_disk_usage)
    monkeypatch.setattr('asyncio.sleep', fake_sleep)

    event = AsyncMock()
    event.reply = AsyncMock()

    await extractor._wait_for_free_space(event)

    assert event.reply.await_count == 2
    warning_msg = event.reply.await_args_list[0][0][0]
    resume_msg = event.reply.await_args_list[1][0][0]
    assert 'Low storage' in warning_msg
    assert 'resuming extraction' in resume_msg


@pytest.mark.asyncio
async def test_streaming_batch_builder_dispatches_batches(tmp_path):
    queue_manager = type('QM', (), {})()
    queue_manager.add_upload_task = AsyncMock()
    queue_manager._wait_for_upload_idle = AsyncMock()

    extractor = type('Extractor', (), {'manifest_path': 'manifest.json'})()
    event = AsyncMock()
    builder = StreamingBatchBuilder(queue_manager, extractor, event, 'Archive.zip', '/tmp/archive.zip')

    def make_entry(idx):
        temp_path = tmp_path / f'f{idx}.jpg'
        temp_path.write_text('data')
        return type('Entry', (), {
            'temp_path': str(temp_path),
            'entry_name': f'photo{idx}.jpg',
            'media_type': 'images'
        })

    for i in range(TELEGRAM_ALBUM_MAX_FILES):
        await builder.add_entry(make_entry(i))

    assert queue_manager.add_upload_task.await_count == 1
    assert queue_manager._wait_for_upload_idle.await_count == 1
    upload_task = queue_manager.add_upload_task.await_args[0][0]
    assert upload_task['cleanup_file_paths'] is True
    assert upload_task['streaming_manifest'] == 'manifest.json'
    assert len(upload_task['file_paths']) == TELEGRAM_ALBUM_MAX_FILES

    await builder.add_entry(make_entry(99))
    await builder.flush()
    assert queue_manager.add_upload_task.await_count == 2


@pytest.mark.asyncio
async def test_wait_for_upload_idle_tracks_active_uploads(monkeypatch):
    upload_started = asyncio.Event()
    upload_can_finish = asyncio.Event()

    async def fake_execute_upload(self, task):
        upload_started.set()
        await upload_can_finish.wait()

    monkeypatch.setattr(QueueManager, '_execute_upload_task', fake_execute_upload)
    queue_manager = QueueManager()

    task = {
        'type': 'grouped_media',
        'media_type': 'images',
        'event': None,
        'file_paths': [],
        'filename': 'Streaming Batch Test',
        'source_archive': 'Archive.zip',
        'is_grouped': True
    }

    await queue_manager.add_upload_task(task)
    await upload_started.wait()

    wait_task = asyncio.create_task(queue_manager._wait_for_upload_idle())
    await asyncio.sleep(0.05)
    assert not wait_task.done()

    upload_can_finish.set()
    await wait_task

    if queue_manager.upload_task:
        queue_manager.upload_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await queue_manager.upload_task
