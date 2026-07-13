from unittest import IsolatedAsyncioTestCase, mock

from tests.fakes import FakeSession, FakeResponse, FakeClientSessionFactory
from nonebot_plugin_bili import client as client_mod
from nonebot_plugin_bili.client import WbiSession, parse_short, close_client, get_content_length


class WbiSessionTests(IsolatedAsyncioTestCase):
    async def test_sign_params_reuses_keys_on_same_date(self):
        from datetime import date

        refreshes = 0

        async def refresh_keys():
            nonlocal refreshes
            refreshes += 1
            return '7cd084941338484aae1ad9425b84077c', '4932caff0ff746eab6f01bf08b70ac45'

        session = WbiSession(refresh_keys=refresh_keys, today=lambda: date(2026, 5, 11))
        first = await session.sign_params({'bvid': 'BV1zWdPBUEwv'})
        second = await session.sign_params({'bvid': 'BV1zWdPBUEwv'})
        self.assertEqual(refreshes, 1)
        self.assertIn('w_rid', first)
        self.assertIn('w_rid', second)

    async def test_sign_params_refreshes_when_date_changes(self):
        from datetime import date

        refreshes = 0
        current_date = date(2026, 5, 11)

        async def refresh_keys():
            nonlocal refreshes
            refreshes += 1
            return '7cd084941338484aae1ad9425b84077c', '4932caff0ff746eab6f01bf08b70ac45'

        session = WbiSession(refresh_keys=refresh_keys, today=lambda: current_date)
        await session.sign_params({'bvid': 'BV1zWdPBUEwv'})
        current_date = date(2026, 5, 12)
        await session.sign_params({'bvid': 'BV1zWdPBUEwv'})
        self.assertEqual(refreshes, 2)


class ParseShortTests(IsolatedAsyncioTestCase):
    async def test_parse_short_success(self):
        session = FakeSession(
            FakeResponse(302, headers={'Location': 'https://www.bilibili.com/video/BV1xx411c7mD/?spm=1'})
        )
        with mock.patch.object(client_mod, 'get_client', mock.AsyncMock(return_value=session)):
            bvid = await parse_short('b23.tv/AbCdEfG')
        self.assertEqual(bvid, 'BV1xx411c7mD')
        self.assertFalse(session.get_calls[0]['allow_redirects'])

    async def test_parse_short_non_redirect(self):
        session = FakeSession(FakeResponse(200, payload={}))
        with mock.patch.object(client_mod, 'get_client', mock.AsyncMock(return_value=session)):
            self.assertIsNone(await parse_short('b23.tv/AbCdEfG'))


class ContentLengthTests(IsolatedAsyncioTestCase):
    async def test_content_range(self):
        session = FakeSession(FakeResponse(206, headers={'Content-Range': 'bytes 0-0/12345'}, body=b'x'))
        factory = FakeClientSessionFactory(session)
        with mock.patch.object(client_mod.aiohttp, 'ClientSession', factory):
            size = await get_content_length('https://example.com/a.mp4')
        self.assertEqual(size, 12345)


class CloseClientTests(IsolatedAsyncioTestCase):
    async def test_close_client(self):
        session = FakeSession()
        session.closed = False
        with mock.patch.object(client_mod, '_client', session):
            await close_client()
            self.assertTrue(session.closed)
            self.assertIsNone(client_mod._client)
