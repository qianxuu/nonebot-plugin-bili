import json
import zlib
from unittest import mock

from nonebot_plugin_bili import live_ws as live_ws_mod
from nonebot_plugin_bili.live_ws import (
    OP_AUTH,
    OP_MESSAGE,
    stop_ws,
    start_ws,
    stop_all_ws,
    _make_packet,
    _parse_packets,
)


def test_make_and_parse_plain_message():
    body = json.dumps({'cmd': 'WATCHED_CHANGE', 'data': {'num': 7}}).encode()
    packet = _make_packet(OP_MESSAGE, body)
    # 手动设置 ver=1 的头：_make_packet 固定 ver=1，正合用
    msgs = _parse_packets(packet)
    assert msgs == [{'cmd': 'WATCHED_CHANGE', 'data': {'num': 7}}]


def test_parse_zlib_nested():
    inner_body = json.dumps({'cmd': 'ONLINE_RANK_COUNT', 'data': {'online_count': 3}}).encode()
    inner = _make_packet(OP_MESSAGE, inner_body)
    compressed = zlib.compress(inner)
    # 构造 ver=2 的外层包
    import struct

    total = 16 + len(compressed)
    header = struct.Struct('>IHHII').pack(total, 16, 2, OP_MESSAGE, 1)
    msgs = _parse_packets(header + compressed)
    assert msgs[0]['cmd'] == 'ONLINE_RANK_COUNT'


def test_start_stop_ws_tasks():
    live_ws_mod._ws_tasks.clear()
    fake_task = mock.Mock()
    fake_task.done.return_value = False

    with mock.patch.object(live_ws_mod.asyncio, 'create_task', return_value=fake_task) as create:
        start_ws(1, 100)
        start_ws(1, 100)  # already running
        create.assert_called_once()
        stop_ws(1)
        fake_task.cancel.assert_called_once()
        stop_all_ws()
    live_ws_mod._ws_tasks.clear()
    assert live_ws_mod._ws_tasks == {}


def test_auth_packet_shape():
    pkt = _make_packet(OP_AUTH, b'{}')
    assert len(pkt) >= 16
