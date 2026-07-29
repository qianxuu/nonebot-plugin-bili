"""HTTP 客户端"""

import re
import asyncio
from datetime import date, datetime, timezone, timedelta
from collections.abc import Callable, Awaitable

import aiohttp
from nonebot import logger

from .wbi import HEADERS, encWbi, getWbiKeys

_client_lock = asyncio.Lock()
_client: aiohttp.ClientSession | None = None


async def get_client() -> aiohttp.ClientSession:
    """获取共享 HTTP 客户端，避免重复创建连接"""

    global _client
    async with _client_lock:
        if _client is None or _client.closed:
            _client = aiohttp.ClientSession()
        return _client


async def close_client() -> None:
    """关闭共享 HTTP 客户端。"""

    global _client
    async with _client_lock:
        if _client is not None and not _client.closed:
            await _client.close()
        _client = None


class WbiSession:
    """WBI 状态会话，封装密钥缓存与刷新逻辑"""

    def __init__(
        self,
        *,
        refresh_keys: Callable[[], Awaitable[tuple[str, str]]] | None = None,
        today: Callable[[], date] = lambda: date.today(),
    ):
        self._img_key: str = ''
        self._sub_key: str = ''
        self._wbi_date: date | None = None
        self._wbi_lock = asyncio.Lock()
        self._refresh_keys = refresh_keys
        self._today = today

    async def sign_params(self, params: dict) -> dict:
        """确保 WBI 密钥可用并对参数签名"""

        today = self._today()
        if self._wbi_date != today or not self._img_key or not self._sub_key:
            await self.refresh_wbi()

        return encWbi(params, self._img_key, self._sub_key)

    async def refresh_wbi(self, *, force: bool = False):
        """刷新 WBI 密钥"""

        async with self._wbi_lock:
            today = self._today()
            if not force and self._wbi_date == today and self._img_key and self._sub_key:
                return

            if self._refresh_keys is None:
                session = await get_client()
                self._img_key, self._sub_key = await getWbiKeys(session=session)
            else:
                self._img_key, self._sub_key = await self._refresh_keys()
            self._wbi_date = today

            logger.info('已刷新 WBI')


_wbi = WbiSession(today=lambda: datetime.now(timezone(timedelta(hours=8))).date())


def _has_voucher(data: dict) -> bool:
    payload = data.get('data')
    return isinstance(payload, dict) and bool(payload.get('v_voucher'))


async def request(url: str, params: dict, timeout: int = 10) -> dict:
    """发送带 WBI 签名的 GET 请求"""

    signed = await _wbi.sign_params(params)

    session = await get_client()
    async with session.get(
        url,
        params=signed,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()

    if _has_voucher(data):
        logger.warning('WBI 请求返回 v_voucher，刷新 WBI 后重试')
        await _wbi.refresh_wbi(force=True)
        signed = await _wbi.sign_params(params)
        async with session.get(
            url,
            params=signed,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if _has_voucher(data):
                logger.error('WBI 重试后仍返回 v_voucher，签名可能已失效')

    return data


async def get(url: str, *, params: dict | None = None, timeout: int = 10) -> dict:
    """发送 GET 请求"""

    session = await get_client()
    async with session.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def post(url: str, *, json: dict | None = None, timeout: int = 10) -> dict:
    """发送 POST 请求"""

    session = await get_client()
    async with session.post(
        url,
        json=json,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def parse_short(short: str) -> str | None:
    """解析短链接"""

    short = 'https://' + short

    # b23.tv 反爬会拒绝无 UA 的请求,带上与 WBI 请求一致的浏览器头;
    # aiohttp 默认会跟随重定向到落地页,这里要的是 302 Location 里的 BV 号,必须关闭跟随
    session = await get_client()
    async with session.get(
        short,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=False,
    ) as resp:
        if resp.status not in (301, 302):
            return None

        match = re.search(r'BV1.{9}', resp.headers.get('Location', ''))
        if match is None:
            return None

        return match.group()
