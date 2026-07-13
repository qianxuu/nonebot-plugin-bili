"""B站直播间 WebSocket 信息流客户端 — 采集观看人数和同接数据"""

import json
import zlib
import struct
import asyncio
import contextlib

import aiohttp
from aiohttp import WSMsgType
from nonebot import logger

from .api import fetch_danmu_info
from .wbi import HEADERS
from .client import get_client
from .database import update_session_watched, update_session_max_online

TAG = '[哔哩直播]'

# -------- 二进制协议 --------

HEADER_SIZE = 16
OP_HEARTBEAT = 2
OP_HEARTBEAT_REPLY = 3
OP_MESSAGE = 5
OP_AUTH = 7
OP_AUTH_REPLY = 8

# >I H H i I  →  total(4) header(2) ver(2) op(4) seq(4)
HEADER_STRUCT = struct.Struct('>IHHII')


def _make_packet(op: int, body: bytes = b'') -> bytes:
    """构造数据包: 16 字节头 + 正文"""

    total = HEADER_SIZE + len(body)
    header = HEADER_STRUCT.pack(total, HEADER_SIZE, 1, op, 1)
    return header + body


def _parse_packets(raw: bytes) -> list[dict]:
    """解析一条或多条嵌套数据包, 返回 JSON 命令列表"""

    messages: list[dict] = []
    offset = 0

    while offset < len(raw):
        if offset + HEADER_SIZE > len(raw):
            break

        total, _hdr_len, ver, op, _seq = HEADER_STRUCT.unpack_from(raw, offset)
        body = raw[offset + HEADER_SIZE : offset + total]
        offset += total

        if op == OP_MESSAGE:
            if ver == 2:
                messages.extend(_parse_packets(zlib.decompress(body)))
            else:
                with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                    messages.append(json.loads(body))
        elif op == OP_AUTH_REPLY:
            with contextlib.suppress(Exception):
                messages.append(json.loads(body))

    return messages


# -------- 直播间数据采集 --------


# uid -> asyncio.Task
_ws_tasks: dict[int, asyncio.Task] = {}


async def _heartbeat_loop(ws: aiohttp.ClientWebSocketResponse, uid: int):
    """每 30 秒发送心跳"""

    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_bytes(_make_packet(OP_HEARTBEAT))
            logger.debug(f'{TAG} 心跳已发送: uid={uid}')
    except (asyncio.CancelledError, aiohttp.ClientConnectionError):
        pass


async def _ws_session(uid: int, room_id: int):
    """单次 WebSocket 会话"""

    info = await fetch_danmu_info(room_id)
    if info is None:
        await asyncio.sleep(10)
        return

    token = info.get('token', '')
    hosts = info.get('host_list', [])
    if not hosts:
        logger.error(f'{TAG} 无可用服务器: uid={uid}')
        await asyncio.sleep(10)
        return

    host = hosts[0]
    uri = f'wss://{host["host"]}:{host["wss_port"]}/sub'

    session = await get_client()
    async with session.ws_connect(uri, headers=HEADERS, autoping=False, heartbeat=None) as ws:
        # 发送认证包
        auth_body = json.dumps(
            {
                'uid': 0,
                'roomid': room_id,
                'protover': 2,
                'platform': 'web',
                'type': 2,
                'key': token,
            },
            separators=(',', ':'),
        ).encode()
        await ws.send_bytes(_make_packet(OP_AUTH, auth_body))

        logger.info(f'{TAG} 已连接: uid={uid}, room={room_id}')

        heartbeat_task = asyncio.create_task(_heartbeat_loop(ws, uid))
        try:
            async for msg in ws:
                if msg.type != WSMsgType.BINARY:
                    continue
                for cmd_msg in _parse_packets(msg.data):
                    cmd = cmd_msg.get('cmd', '')
                    if cmd == 'WATCHED_CHANGE':
                        num = cmd_msg.get('data', {}).get('num', 0)
                        update_session_watched(uid, num)
                        logger.debug(f'{TAG} WATCHED_CHANGE: uid={uid}, num={num}')
                    elif cmd == 'ONLINE_RANK_COUNT':
                        online = cmd_msg.get('data', {}).get('online_count', 0)
                        update_session_max_online(uid, online)
                        logger.debug(f'{TAG} ONLINE_RANK_COUNT: uid={uid}, online={online}')
        except aiohttp.ClientConnectionError as e:
            # 服务端主动断开 / keepalive 超时,让外层 _ws_loop 决定是否重连
            logger.warning(f'{TAG} 连接已断开: uid={uid}, {e}')
        finally:
            heartbeat_task.cancel()


async def _ws_loop(uid: int, room_id: int):
    """持续 WebSocket 连接（含自动重连）"""

    while True:
        try:
            await _ws_session(uid, room_id)
        except asyncio.CancelledError:
            logger.info(f'{TAG} 任务已取消: uid={uid}')
            return
        except Exception as e:
            logger.warning(f'{TAG} 连接异常: uid={uid}, {e}, 5 秒后重连')
            await asyncio.sleep(5)


# -------- 对外接口 --------


def start_ws(uid: int, room_id: int):
    """开播时调用：启动 WebSocket 采集任务"""

    if uid in _ws_tasks and not _ws_tasks[uid].done():
        return

    _ws_tasks[uid] = asyncio.create_task(_ws_loop(uid, room_id))
    logger.info(f'{TAG} 启动采集: uid={uid}, room={room_id}')


def stop_ws(uid: int):
    """下播时调用：停止 WebSocket 采集任务"""

    task = _ws_tasks.pop(uid, None)
    if task and not task.done():
        task.cancel()
    logger.info(f'{TAG} 停止采集: uid={uid}')


def stop_all_ws() -> None:
    """停止全部 WebSocket 采集任务。"""

    for uid in list(_ws_tasks):
        stop_ws(uid)
