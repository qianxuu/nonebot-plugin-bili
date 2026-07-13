from types import SimpleNamespace
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase, mock

from tests.fakes import FakeBot
from nonebot_plugin_bili import live as live_mod
from nonebot_plugin_bili.live import (
    send_live_stop,
    handle_sub_list,
    send_live_start,
    handle_subscribe,
    poll_live_status,
    send_title_change,
    handle_unsubscribe,
)
from nonebot_plugin_bili.database import LiveSession


def _session(**overrides: Any) -> LiveSession:
    base: dict[str, Any] = {
        'uid': 1,
        'live_time': 1000,
        'title': 't',
        'cover': 'https://i0/c.jpg',
        'room_id': 9,
        'uname': '主播',
        'notified_start': 1,
        'notified_stop': 0,
        'watched': 10,
        'max_online': 3,
    }
    base.update(overrides)
    return cast(LiveSession, base)


class NotifyTests(IsolatedAsyncioTestCase):
    async def test_send_live_start_and_stop(self):
        bot = FakeBot()
        session = _session()
        with (
            mock.patch.object(live_mod, 'get_sub_groups', return_value=[11, 12]),
            mock.patch.object(live_mod, 'get_last_stopped_session', return_value=None),
            mock.patch.object(live_mod, 'get_bot', return_value=bot),
            mock.patch.object(live_mod.time, 'time', return_value=1900),
        ):
            await send_live_start(1, session)
            await send_live_stop(1, session)
            await send_title_change(1, '主播', 9, 'old', 'new')
        self.assertEqual(len(bot.group_msgs), 6)

    async def test_no_groups_noop(self):
        with mock.patch.object(live_mod, 'get_sub_groups', return_value=[]):
            await send_live_start(1, _session(uname='a', title='t', cover='', room_id=1, live_time=1))


class CommandTests(IsolatedAsyncioTestCase):
    async def test_subscribe_format_error(self):
        bot = FakeBot()
        ev = SimpleNamespace(get_plaintext=lambda: '订阅直播 bad')
        await handle_subscribe(cast(Any, bot), cast(Any, ev))
        self.assertIn('格式', str(bot.sent[0][1]))

    async def test_subscribe_success(self):
        bot = FakeBot()
        ev = SimpleNamespace(get_plaintext=lambda: '订阅直播 123 456')

        async def fake_status(uids):
            return {'123': {'uname': '主播A', 'title': 't'}}

        with (
            mock.patch.object(live_mod, 'fetch_live_status', fake_status),
            mock.patch.object(live_mod, 'add_sub', return_value=True),
        ):
            await handle_subscribe(cast(Any, bot), cast(Any, ev))
        self.assertIn('已订阅', str(bot.sent[0][1]))

    async def test_unsubscribe_and_list(self):
        bot = FakeBot()
        ev = SimpleNamespace(get_plaintext=lambda: '取消订阅直播 1 2')
        with (
            mock.patch.object(live_mod, 'remove_sub', return_value=True),
            mock.patch.object(live_mod, 'get_sub_groups', return_value=[]),
            mock.patch.object(live_mod, 'get_active_session', return_value=None),
        ):
            await handle_unsubscribe(cast(Any, bot), cast(Any, ev))
        self.assertIn('已取消订阅', str(bot.sent[0][1]))

        bot2 = FakeBot()
        with mock.patch.object(
            live_mod,
            'get_all_subs',
            return_value=[{'uid': 1, 'group_id': 2, 'uname': 'A'}, {'uid': 1, 'group_id': 3, 'uname': 'A'}],
        ):
            await handle_sub_list(cast(Any, bot2), cast(Any, SimpleNamespace()))
        self.assertIn('共订阅 1 个主播', str(bot2.sent[0][1]))


class PollTests(IsolatedAsyncioTestCase):
    async def test_poll_detects_start(self):
        calls: list[str] = []
        active_calls = {'n': 0}

        async def fake_fetch(uids):
            return {
                '1': {
                    'live_status': 1,
                    'live_time': 100,
                    'uname': 'U',
                    'title': 'T',
                    'room_id': 9,
                    'cover_from_user': 'c',
                }
            }

        def fake_active(uid):
            # 首次用于补发下播判断 -> None；insert 后再次查询 -> 未通知会话
            active_calls['n'] += 1
            if active_calls['n'] == 1:
                return None
            return {
                'uid': 1,
                'live_time': 100,
                'title': 'T',
                'cover': 'c',
                'room_id': 9,
                'uname': 'U',
                'notified_start': 0,
                'notified_stop': 0,
                'watched': 0,
                'max_online': 0,
            }

        async def fake_send_start(uid, session):
            calls.append('start')

        with (
            mock.patch.object(live_mod, 'get_all_sub_uids', return_value=[1]),
            mock.patch.object(live_mod, 'fetch_live_status', fake_fetch),
            mock.patch.object(live_mod, 'get_sub_title', return_value='T'),
            mock.patch.object(live_mod, 'get_active_session', side_effect=fake_active),
            mock.patch.object(live_mod, 'insert_session'),
            mock.patch.object(live_mod, 'start_ws'),
            mock.patch.object(live_mod, 'send_live_start', fake_send_start),
            mock.patch.object(live_mod, 'mark_start_notified') as mark,
        ):
            await poll_live_status()
        self.assertIn('start', calls)
        mark.assert_called()
