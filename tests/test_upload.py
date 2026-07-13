from typing import cast
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from nonebot.adapters.onebot.v11 import Bot

from tests.fakes import FakeBot
from nonebot_plugin_bili.upload import UploadOptions, upload_file_stream


class UploadTests(IsolatedAsyncioTestCase):
    async def test_upload_file_stream_chunks(self):
        path = Path('cache/bili-upload-test.bin')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'0123456789')
        bot = FakeBot()
        try:
            uploaded = await upload_file_stream(cast(Bot, bot), path, options=UploadOptions(chunk_size=4))
            self.assertTrue(uploaded.startswith('/tmp/uploaded-'))
            # 3 data chunks + 1 complete
            self.assertEqual(len(bot.api_calls), 4)
            self.assertTrue(bot.api_calls[-1].get('is_complete'))
        finally:
            path.unlink(missing_ok=True)
