from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

from nonebot_plugin_bili import api as api_mod
from nonebot_plugin_bili.api import (
    _is_pcdn,
    get_video_info,
    fetch_danmu_info,
    fetch_live_status,
    get_video_stream_info,
)


class IsPcdnTests(IsolatedAsyncioTestCase):
    def test_detects_bcache_os(self):
        self.assertTrue(_is_pcdn('https://example.com/x?os=bcache&x=1'))
        self.assertFalse(_is_pcdn('https://example.com/x?os=upos'))
        self.assertFalse(_is_pcdn('not a url'))


class LiveStatusTests(IsolatedAsyncioTestCase):
    async def test_returns_empty_dict_when_live_status_payload_is_empty_list(self):
        async def fake_post(_url, *, json):
            return {'code': 0, 'message': 'OK', 'data': []}

        with (
            mock.patch('nonebot_plugin_bili.api.post', fake_post),
            mock.patch('nonebot_plugin_bili.api.logger.error') as log_error,
        ):
            status = await fetch_live_status([123])

        self.assertEqual(status, {})
        log_error.assert_not_called()

    async def test_returns_none_when_live_status_payload_is_non_empty_list(self):
        async def fake_post(_url, *, json):
            return {'code': 0, 'message': 'OK', 'data': [{'uid': 123}]}

        with (
            mock.patch('nonebot_plugin_bili.api.post', fake_post),
            mock.patch('nonebot_plugin_bili.api.logger.error') as log_error,
        ):
            status = await fetch_live_status([123])

        self.assertIsNone(status)
        self.assertIn('data 字段类型异常: list', log_error.call_args.args[0])

    async def test_returns_payload_dict(self):
        async def fake_post(_url, *, json):
            return {'code': 0, 'data': {'1': {'live_status': 1}}}

        with mock.patch('nonebot_plugin_bili.api.post', fake_post):
            status = await fetch_live_status([1])
        self.assertEqual(status, {'1': {'live_status': 1}})

    async def test_code_nonzero_returns_none(self):
        async def fake_post(_url, *, json):
            return {'code': -1, 'message': 'fail'}

        with mock.patch('nonebot_plugin_bili.api.post', fake_post):
            self.assertIsNone(await fetch_live_status([1]))


class VideoStreamInfoTests(IsolatedAsyncioTestCase):
    async def test_returns_fallback_when_playurl_has_voucher_without_durl(self):
        async def fake_request(_url, _params):
            return {
                'code': 0,
                'message': 'OK',
                'data': {'v_voucher': 'voucher_11111111-1111-1111-1111-111111111111'},
            }

        with (
            mock.patch('nonebot_plugin_bili.api.request', fake_request),
            mock.patch('nonebot_plugin_bili.api.logger.error') as log_error,
        ):
            stream = await get_video_stream_info('BV1zWdPBUEwv', 38165743520)

        self.assertTrue(stream.skip_download)
        self.assertEqual(stream.skip_download_msg, '请前往哔哩哔哩观看')
        self.assertIsNone(stream.url)
        self.assertIn('v_voucher', log_error.call_args.args[0])
        self.assertNotIn("'durl'", log_error.call_args.args[0])

    async def test_charge_only_code(self):
        async def fake_request(_url, _params):
            return {'code': 87008, 'message': 'charge'}

        with mock.patch('nonebot_plugin_bili.api.request', fake_request):
            stream = await get_video_stream_info('BV1', 1)
        self.assertTrue(stream.skip_download)
        self.assertIn('充电专属', stream.skip_download_msg or '')

    async def test_too_large_video(self):
        async def fake_request(_url, _params):
            return {
                'code': 0,
                'data': {
                    'durl': [
                        {
                            'size': api_mod.BILI_MAX_VIDEO_SIZE + 1,
                            'url': 'https://upos.example.com/a?os=upos',
                        }
                    ]
                },
            }

        with mock.patch('nonebot_plugin_bili.api.request', fake_request):
            stream = await get_video_stream_info('BV1', 1)
        self.assertTrue(stream.skip_download)
        self.assertIn('较大', stream.skip_download_msg or '')

    async def test_skips_pcdn_and_uses_backup(self):
        async def fake_request(_url, _params):
            return {
                'code': 0,
                'data': {
                    'durl': [
                        {
                            'size': 1024,
                            'url': 'https://pcdn.example.com/a?os=bcache',
                            'backup_url': ['https://upos.example.com/b?os=upos'],
                        }
                    ]
                },
            }

        with mock.patch('nonebot_plugin_bili.api.request', fake_request):
            stream = await get_video_stream_info('BV1', 1)
        self.assertFalse(stream.skip_download)
        self.assertEqual(stream.url, 'https://upos.example.com/b?os=upos')


class GetVideoInfoTests(IsolatedAsyncioTestCase):
    async def test_uses_cached_skip_stream(self, tmp_path: Path | None = None):
        view = {
            'code': 0,
            'data': {
                'pic': 'https://i0/pic.jpg',
                'title': 't',
                'owner': {'name': 'u'},
                'pubdate': 1,
                'duration': 2,
                'cid': 99,
                'stat': {'view': 1, 'like': 2, 'coin': 3, 'favorite': 4, 'share': 5},
            },
        }

        async def fake_request(url, params):
            self.assertIn('view', url)
            return view

        cache = mock.Mock()
        cache.exists.return_value = True
        with (
            mock.patch('nonebot_plugin_bili.api.request', fake_request),
            mock.patch('nonebot_plugin_bili.api.get_cache_file_path', return_value=cache),
            mock.patch('nonebot_plugin_bili.api.get_video_stream_info', mock.AsyncMock()) as stream_mock,
        ):
            info = await get_video_info('BV1xx411c7mD')
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.title, 't')
        self.assertTrue(info.stream.skip_download)
        stream_mock.assert_not_called()


class DanmuInfoTests(IsolatedAsyncioTestCase):
    async def test_fetch_danmu_info_ok(self):
        async def fake_request(url, params):
            return {'code': 0, 'data': {'token': 't', 'host_list': []}}

        with mock.patch('nonebot_plugin_bili.api.request', fake_request):
            data = await fetch_danmu_info(123)
        self.assertEqual(data, {'token': 't', 'host_list': []})
