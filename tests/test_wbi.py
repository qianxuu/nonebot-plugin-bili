from typing import cast
from unittest import IsolatedAsyncioTestCase, mock

import aiohttp

from tests.fakes import FakeSession, FakeResponse
from nonebot_plugin_bili.wbi import encWbi, getWbiKeys, getMixinKey


def test_get_mixin_key_length_and_deterministic():
    key = getMixinKey('a' * 64)
    assert len(key) == 32
    assert getMixinKey('a' * 64) == key


def test_enc_wbi_adds_wts_and_w_rid():
    # img_key + sub_key 需足够长以覆盖 mixin 表下标 0..63
    img_key = '7cd084941338484aae1ad9425b84077c'
    sub_key = '4932caff0ff746eab6f01bf08b70ac45'
    with mock.patch('nonebot_plugin_bili.wbi.time.time', return_value=1_700_000_000):
        signed = encWbi({'bvid': 'BV1xx411c7mD', 'foo': "a!'()*b"}, img_key, sub_key)
    assert 'wts' in signed
    assert 'w_rid' in signed
    assert '!' not in signed['foo']
    assert signed['bvid'] == 'BV1xx411c7mD'


class GetWbiKeysTests(IsolatedAsyncioTestCase):
    async def test_get_wbi_keys_parses_urls(self):
        payload = {
            'data': {
                'wbi_img': {
                    'img_url': 'https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png',
                    'sub_url': 'https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png',
                }
            }
        }
        session = FakeSession(FakeResponse(200, payload=payload))
        img, sub = await getWbiKeys(session=cast(aiohttp.ClientSession, session))
        self.assertEqual(img, '7cd084941338484aae1ad9425b84077c')
        self.assertEqual(sub, '4932caff0ff746eab6f01bf08b70ac45')
