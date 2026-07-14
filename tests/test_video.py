import json
from types import SimpleNamespace
from typing import cast
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent

from tests.fakes import FakeBot
from nonebot_plugin_bili import video as video_mod
from nonebot_plugin_bili.api import VideoInfo, VideoStreamInfo
from nonebot_plugin_bili.video import handle_video, send_video_info


def _make_event(*, plain: str = '', group_id: int | None = None, card: dict | None = None):
    msg_seg = SimpleNamespace(data={'data': json.dumps(card or {}, ensure_ascii=False)})

    class Ev:
        def get_plaintext(self):
            return plain

        def get_message(self):
            return [msg_seg]

    if group_id is None:
        return Ev()

    # 不真正构造 GroupMessageEvent（pydantic 复杂），用 duck typing + isinstance patch
    return SimpleNamespace(
        get_plaintext=lambda: plain,
        get_message=lambda: [msg_seg],
        group_id=group_id,
    )


class HandleVideoTests(IsolatedAsyncioTestCase):
    async def test_blacklist_skips(self):
        bot = FakeBot()
        # 非黑名单时会继续，这里 mock 后续
        ev2 = SimpleNamespace(
            group_id=1,
            get_plaintext=lambda: 'see BV1xx411c7mD here',
            get_message=lambda: [],
        )

        async def fake_process(bot, ev, bvid):
            processed.append(bvid)

        processed: list[str] = []
        with (
            mock.patch.object(video_mod, 'BILI_GROUP_BLACKLIST', {999}),
            mock.patch.object(video_mod, 'GroupMessageEvent', type(ev2)),
            mock.patch.object(video_mod, 'is_bvid_in_cd', return_value=False),
            mock.patch.object(video_mod, '_process_bvid', fake_process),
        ):
            real_isinstance = isinstance

            def fake_isinstance(obj, typ):
                if typ is video_mod.GroupMessageEvent:
                    return hasattr(obj, 'group_id')
                return real_isinstance(obj, typ)

            with mock.patch('nonebot_plugin_bili.video.isinstance', fake_isinstance):
                await handle_video(cast(Bot, bot), cast(MessageEvent, ev2))
        self.assertEqual(processed, ['BV1xx411c7mD'])

    async def test_short_link_resolution(self):
        bot = FakeBot()
        ev = SimpleNamespace(
            group_id=2,
            get_plaintext=lambda: 'https://b23.tv/AbCdEfG',
            get_message=lambda: [],
        )
        processed: list[str] = []

        async def fake_parse(short: str):
            return 'BV1yy411c7mE'

        async def fake_process(bot, ev, bvid):
            processed.append(bvid)

        real_isinstance = isinstance

        def fake_isinstance(obj, typ):
            if typ is video_mod.GroupMessageEvent:
                return hasattr(obj, 'group_id')
            return real_isinstance(obj, typ)

        with (
            mock.patch.object(video_mod, 'parse_short', fake_parse),
            mock.patch.object(video_mod, 'is_bvid_in_cd', return_value=False),
            mock.patch.object(video_mod, '_process_bvid', fake_process),
            mock.patch('nonebot_plugin_bili.video.isinstance', fake_isinstance),
        ):
            await handle_video(cast(Bot, bot), cast(MessageEvent, ev))
        self.assertEqual(processed, ['BV1yy411c7mE'])


class SendVideoInfoTests(IsolatedAsyncioTestCase):
    async def test_send_info_and_skip_download(self):
        bot = FakeBot()
        ev = SimpleNamespace()
        data = VideoInfo(
            bvid='BV1xx411c7mD',
            pic='https://i0/pic.jpg',
            title='hello',
            owner_name='u',
            pubdate=1,
            duration=2,
            view=3,
            like=4,
            coin=5,
            favorite=6,
            share=7,
            stream=VideoStreamInfo(skip_download=True, skip_download_msg='视频较大，请前往哔哩哔哩观看'),
        )
        cache = mock.Mock()
        cache.exists.return_value = False
        with (
            mock.patch.object(video_mod, 'BILI_SEND_COVER', True),
            mock.patch.object(video_mod, 'BILI_SEND_VIDEO', True),
            mock.patch.object(video_mod, 'get_cache_file_path', return_value=cache),
        ):
            await send_video_info(cast(Bot, bot), cast(MessageEvent, ev), data)
        self.assertEqual(len(bot.sent), 1)
        _event, msg = bot.sent[0]
        self.assertIsInstance(msg, Message)
        self.assertIn('视频较大', str(msg))

    async def test_send_cover_only_skips_video(self):
        bot = FakeBot()
        ev = SimpleNamespace()
        data = VideoInfo(
            bvid='BV1aa411c7mA',
            pic='https://i0/pic.jpg',
            title='cover-only',
            owner_name='u',
            pubdate=1,
            duration=2,
            view=3,
            like=4,
            coin=5,
            favorite=6,
            share=7,
            stream=VideoStreamInfo(skip_download=False, url='https://example.com/v.mp4'),
        )
        with (
            mock.patch.object(video_mod, 'BILI_SEND_COVER', True),
            mock.patch.object(video_mod, 'BILI_SEND_VIDEO', False),
            mock.patch.object(video_mod, 'download', side_effect=AssertionError('should not download')),
        ):
            await send_video_info(cast(Bot, bot), cast(MessageEvent, ev), data)
        self.assertEqual(len(bot.sent), 1)
        _event, msg = bot.sent[0]
        self.assertIn('cover-only', str(msg))
        self.assertTrue(any(seg.type == 'image' for seg in msg))

    async def test_send_video_without_cover(self):
        bot = FakeBot()
        ev = SimpleNamespace()
        path = Path('cache/bili-send-no-cover.mp4')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'1234')
        data = VideoInfo(
            bvid='BV1bb411c7mB',
            pic='https://i0/pic.jpg',
            title='no-cover',
            owner_name='u',
            pubdate=1,
            duration=2,
            view=3,
            like=4,
            coin=5,
            favorite=6,
            share=7,
            stream=VideoStreamInfo(skip_download=False, url='https://example.com/v.mp4'),
        )
        try:
            with (
                mock.patch.object(video_mod, 'BILI_SEND_COVER', False),
                mock.patch.object(video_mod, 'BILI_SEND_VIDEO', True),
                mock.patch.object(video_mod, 'get_cache_file_path', return_value=path),
                mock.patch.object(video_mod, 'get_napcat_cache_file_path', return_value=Path('/app/temp/x.mp4')),
            ):
                await send_video_info(cast(Bot, bot), cast(MessageEvent, ev), data)
            # 未启用 cover：不发标题/封面/链接，只发视频
            self.assertEqual(len(bot.sent), 1)
            _event, video_msg = bot.sent[0]
            self.assertEqual(getattr(video_msg, 'type', None), 'video')
        finally:
            path.unlink(missing_ok=True)

    async def test_send_with_napcat_mapping(self, tmp_path: Path | None = None):
        bot = FakeBot()
        ev = SimpleNamespace()
        path = Path('cache/bili-send-test.mp4')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'1234')
        data = VideoInfo(
            bvid='BV1zz411c7mF',
            pic='https://i0/pic.jpg',
            title='v',
            owner_name='u',
            pubdate=1,
            duration=2,
            view=3,
            like=4,
            coin=5,
            favorite=6,
            share=7,
            stream=VideoStreamInfo(skip_download=False, url='https://example.com/v.mp4'),
        )
        try:
            with (
                mock.patch.object(video_mod, 'BILI_SEND_COVER', True),
                mock.patch.object(video_mod, 'BILI_SEND_VIDEO', True),
                mock.patch.object(video_mod, 'get_cache_file_path', return_value=path),
                mock.patch.object(video_mod, 'get_napcat_cache_file_path', return_value=Path('/app/temp/x.mp4')),
            ):
                await send_video_info(cast(Bot, bot), cast(MessageEvent, ev), data)
            self.assertEqual(len(bot.sent), 2)  # info + video
        finally:
            path.unlink(missing_ok=True)
