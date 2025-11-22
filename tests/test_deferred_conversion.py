import os
import pytest

from utils.queue_manager import QueueManager


@pytest.mark.asyncio
async def test_defer_incompatible_videos_creates_tasks(tmp_path):
    queue_manager = QueueManager()
    queue_manager._disable_upload_worker_start = True
    queue_manager.upload_persistent.add_item = lambda item: None  # avoid disk writes

    compatible = tmp_path / "video_good.mp4"
    incompatible = tmp_path / "video_bad.avi"
    compatible.write_text("ok")
    incompatible.write_text("no")

    base_task = {
        'filename': 'album',
        'media_type': 'videos',
        'file_paths': [str(compatible), str(incompatible)],
    }

    queued = []

    async def spy_add(task):
        queued.append(task)

    queue_manager.add_upload_task = spy_add  # type: ignore

    handled = await queue_manager._defer_incompatible_videos(base_task, [str(compatible), str(incompatible)])
    assert handled is True

    grouped = [t for t in queued if t.get('type') != 'deferred_conversion']
    deferred = [t for t in queued if t.get('type') == 'deferred_conversion']

    assert grouped, "Compatible videos should be regrouped"
    assert grouped[0].get('is_grouped') is True
    assert grouped[0]['file_paths'] == [str(compatible)]

    assert deferred, "Incompatible videos should be deferred"
    assert deferred[0]['file_path'] == str(incompatible)


@pytest.mark.asyncio
async def test_deferred_conversion_waits_for_priority(tmp_path):
    queue_manager = QueueManager()
    queue_manager._disable_upload_worker_start = True
    queue_manager.upload_persistent.add_item = lambda item: None  # avoid disk writes

    # Pending normal task indicates priority work remains
    queue_manager.upload_queue.put_nowait({'type': 'direct_media', 'filename': 'normal'})

    conversion_task = {
        'type': 'deferred_conversion',
        'filename': 'later',
        'file_path': str(tmp_path / "pending.mkv")
    }

    handled = await queue_manager._execute_deferred_conversion(conversion_task)
    assert handled is False

    # Deferred task should be re-queued for later
    assert any(item.get('type') == 'deferred_conversion' for item in queue_manager.upload_queue)
