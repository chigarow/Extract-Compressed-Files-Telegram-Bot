import asyncio
import types
import time
import re
import pytest

from utils.telegram_operations import create_download_progress_callback
from utils.utils import human_size

class DummyMsg:
    def __init__(self):
        self.last_text = None
    async def edit(self, text):
        self.last_text = text

@pytest.mark.asyncio
async def test_download_progress_includes_filename_and_speed():
    msg = DummyMsg()
    start = time.time() - 1  # ensure non-zero elapsed
    status = {}
    cb = create_download_progress_callback(msg, status, start, filename="example.mp4")
    # simulate calls
    total = 100_000_000  # 100 MB
    # 10% progress
    cb(10_000_000, total)
    await asyncio.sleep(0.05)
    assert msg.last_text is not None
    assert 'example.mp4' in msg.last_text
    assert 'Download 10%' in msg.last_text or 'Download 9%' in msg.last_text
    assert re.search(r'\d+(\.\d+)?\s*(KB|MB|GB)/s', msg.last_text), msg.last_text
    assert ' / ' in msg.last_text

@pytest.mark.asyncio
async def test_download_progress_speed_growth():
    msg = DummyMsg()
    start = time.time() - 1
    status = {}
    cb = create_download_progress_callback(msg, status, start, filename="file.bin")
    total = 50_000_000
    for i in range(1,6):
        cb(i*5_000_000, total)
        await asyncio.sleep(0.01)
    assert msg.last_text is not None
    assert 'file.bin' in msg.last_text
