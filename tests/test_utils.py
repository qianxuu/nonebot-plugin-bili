import asyncio
from unittest import IsolatedAsyncioTestCase, mock

from nonebot_plugin_bili import utils as utils_mod
from nonebot_plugin_bili.utils import KeyedLock, bytes_to_mib, is_bvid_in_cd, bytes_to_mibps


def test_bytes_helpers():
    assert bytes_to_mib(1024 * 1024) == 1.0
    assert bytes_to_mibps(1024 * 1024, 2) == 0.5
    assert bytes_to_mibps(1024 * 1024, 0) == 0.0


def test_is_bvid_in_cd_and_expiry():
    utils_mod.bvid_cd_list.clear()
    with mock.patch('nonebot_plugin_bili.utils.time.time', return_value=1000):
        assert is_bvid_in_cd('BV1', 1, seconds=10) is False
        assert is_bvid_in_cd('BV1', 1, seconds=10) is True
        assert is_bvid_in_cd('BV1', 2, seconds=10) is False

    with mock.patch('nonebot_plugin_bili.utils.time.time', return_value=1020):
        assert is_bvid_in_cd('BV1', 1, seconds=10) is False
        assert is_bvid_in_cd('BV1', 1, seconds=10) is True


def test_is_bvid_in_cd_zero_seconds_disables_cd():
    utils_mod.bvid_cd_list.clear()
    with mock.patch('nonebot_plugin_bili.utils.time.time', return_value=1000):
        assert is_bvid_in_cd('BV2', 1, seconds=0) is False
        assert is_bvid_in_cd('BV2', 1, seconds=0) is False


class KeyedLockTests(IsolatedAsyncioTestCase):
    async def test_same_key_is_serialized(self):
        lock = KeyedLock()
        order: list[str] = []

        async def worker(name: str):
            async with lock('k'):
                order.append(f'{name}-enter')
                await asyncio.sleep(0.01)
                order.append(f'{name}-exit')

        await asyncio.gather(worker('a'), worker('b'))
        self.assertIn(order, (['a-enter', 'a-exit', 'b-enter', 'b-exit'], ['b-enter', 'b-exit', 'a-enter', 'a-exit']))
