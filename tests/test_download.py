import time
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

from tests.fakes import FakeSession, FakeResponse, FakeClientSessionFactory
from nonebot_plugin_bili import download as download_mod
from nonebot_plugin_bili.download import download, _prune_cache, get_cache_file_path, _calculate_chunk_count


def test_calculate_chunk_count():
    assert _calculate_chunk_count(1) == 1
    assert _calculate_chunk_count(2 * 1024 * 1024) == 1
    assert _calculate_chunk_count(2 * 1024 * 1024 + 1) == 2
    assert _calculate_chunk_count(100 * 1024 * 1024) == 8


def test_get_cache_file_path():
    path = get_cache_file_path('BV1xx411c7mD')
    assert path.name == 'BV1xx411c7mD.mp4'
    assert path.parts[-2:] == ('bili', 'BV1xx411c7mD.mp4')


def test_prune_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(download_mod, 'BILI_CACHE_RETENTION_SECONDS', 10)
    old = tmp_path / 'old.mp4'
    new = tmp_path / 'new.mp4'
    old.write_bytes(b'a')
    new.write_bytes(b'b')
    now = time.time()
    # old mtime far in past
    import os

    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))
    _prune_cache(tmp_path, now=now)
    assert not old.exists()
    assert new.exists()

    _prune_cache(tmp_path / 'missing', now=now)


class DownloadTests(IsolatedAsyncioTestCase):
    async def test_download_uses_cache(self, tmp_path: Path | None = None):
        cache_dir = Path('cache/bili-test-download')
        cache_dir.mkdir(parents=True, exist_ok=True)
        bvid = 'BV1CACHE0001'
        file_path = cache_dir / f'{bvid}.mp4'
        file_path.write_bytes(b'cached')

        with (
            mock.patch.object(download_mod, '_CACHE_DIR', cache_dir),
            mock.patch.object(download_mod, 'get_content_length', mock.AsyncMock()) as cl,
        ):
            result = await download(bvid, 'https://example.com/v.mp4')
        self.assertEqual(result, file_path)
        cl.assert_not_called()
        file_path.unlink(missing_ok=True)
        cache_dir.rmdir()

    async def test_download_writes_file(self):
        cache_dir = Path('cache/bili-test-download2')
        if cache_dir.exists():
            for p in cache_dir.iterdir():
                p.unlink()
            cache_dir.rmdir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        bvid = 'BV1DL0000001'
        body = b'0123456789abcdef'
        session = FakeSession(FakeResponse(200, body=body))
        factory = FakeClientSessionFactory(session)

        with (
            mock.patch.object(download_mod, '_CACHE_DIR', cache_dir),
            mock.patch.object(download_mod, 'get_content_length', mock.AsyncMock(return_value=len(body))),
            mock.patch.object(download_mod.aiohttp, 'ClientSession', factory),
            mock.patch.object(download_mod, '_calculate_chunk_count', return_value=1),
        ):
            result = await download(bvid, 'https://example.com/v.mp4')

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.read_bytes(), body)
        for p in cache_dir.iterdir():
            p.unlink()
        cache_dir.rmdir()
