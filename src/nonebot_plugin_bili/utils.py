import time
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from nonebot import logger

from .config import BILI_GROUP_CD_SECONDS


class KeyedLock:
    """按 key 分组的锁管理器，引用计数归零时自动清理"""

    def __init__(self):
        self._state: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def __call__(self, key: str):
        lock, refs = self._state.get(key, (asyncio.Lock(), 0))
        self._state[key] = (lock, refs + 1)

        try:
            async with lock:
                yield
        finally:
            lock, refs = self._state[key]
            if refs == 1:
                del self._state[key]
            else:
                self._state[key] = (lock, refs - 1)


@dataclass
class BvidCdItem:
    """视频冷却项"""

    bvid: str = ''
    group_id: int = 0
    expire_time: int = 0


bvid_cd_list: list[BvidCdItem] = []

MIB = 1024 * 1024


def bytes_to_mib(size: int) -> float:
    """将字节数转换为 MiB"""

    return size / MIB


def bytes_to_mibps(size: int, seconds: float) -> float:
    """将字节/秒转换为 MiB/s，自动处理零时长"""

    if seconds <= 0:
        return 0.0
    return bytes_to_mib(size) / seconds


def is_bvid_in_cd(bvid: str, group_id: int, seconds: int | None = None) -> bool:
    """检查 bvid 是否在冷却列表中。

    返回 True 表示仍在冷却中，应跳过发送；
    返回 False 表示未命中，并写入新的冷却项。
    seconds <= 0 时视为关闭冷却，始终返回 False。
    """

    global bvid_cd_list
    cd_seconds = BILI_GROUP_CD_SECONDS if seconds is None else seconds
    if cd_seconds <= 0:
        return False

    now = int(time.time())
    bvid_cd_list = [item for item in bvid_cd_list if item.expire_time > now]
    logger.debug(f'冷却列表: {bvid_cd_list}')

    for item in bvid_cd_list:
        if item.bvid == bvid and item.group_id == group_id:
            return True

    bvid_cd_list.append(BvidCdItem(bvid=bvid, group_id=group_id, expire_time=now + cd_seconds))
    return False
