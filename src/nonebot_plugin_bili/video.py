import re
import json
import time
import asyncio

from nonebot import on_regex
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment, GroupMessageEvent

from .api import VideoInfo, get_video_info
from .utils import KeyedLock, is_bvid_in_cd, bytes_to_mibps
from .client import parse_short
from .config import BILI_GROUP_BLACKLIST, BILI_GROUP_CD_SECONDS, get_napcat_cache_file_path
from .upload import UploadOptions, upload_file_stream
from .download import download, get_cache_file_path

TAG = '[哔哩视频]'

bvid_regex = r'BV1[a-km-zA-HJ-NP-Z1-9]{9}'
short_regex = r'b23\.tv\/[a-zA-Z0-9]{7}(?![a-zA-Z0-9])'
_send_video_lock = KeyedLock()


@on_regex(r'BV1|b23\.tv').handle()
async def handle_video(bot: Bot, ev: MessageEvent):
    """识别 BV 号和短链接"""

    if isinstance(ev, GroupMessageEvent) and ev.group_id in BILI_GROUP_BLACKLIST:
        logger.info(f'{TAG} 群黑名单跳过: {ev.group_id}')
        return

    bvids: list[str] = []
    shorts: list[str] = []

    if ev.get_plaintext() == '':
        data = json.loads(ev.get_message()[0].data.get('data', '{}'))
        logger.debug(f'卡片消息: {data}')
        bvids.extend(re.findall(bvid_regex, str(data)))
        shorts.extend(re.findall(short_regex, str(data)))
    else:
        match_bvids = re.findall(bvid_regex, ev.get_plaintext())
        bvids.extend(match_bvids)
        match_shorts = re.findall(short_regex, ev.get_plaintext())
        shorts.extend(match_shorts)

    if shorts:
        results = await asyncio.gather(*(parse_short(short) for short in shorts))
        for short, bvid in zip(shorts, results, strict=False):
            if bvid is None:
                logger.warning(f'解析失败: {short}')
                continue
            logger.info(f'解析成功: {short} - {bvid}')
            bvids.append(bvid)

    bvids = list(dict.fromkeys(bvids))

    tasks = []
    for bvid in bvids:
        if isinstance(ev, GroupMessageEvent) and is_bvid_in_cd(bvid, ev.group_id, seconds=BILI_GROUP_CD_SECONDS):
            logger.warning(f'群组冷却: {ev.group_id} - {bvid}')
            continue

        logger.info(f'开始获取信息: {bvid}')
        tasks.append(_process_bvid(bot, ev, bvid))

    if tasks:
        logger.info(f'并发处理 {len(tasks)} 个视频')
        await asyncio.gather(*tasks)


async def _process_bvid(bot: Bot, ev: MessageEvent, bvid: str):
    """处理 BV 号"""

    data = await get_video_info(bvid)
    if data is not None:
        await send_video_info(bot, ev, data)


async def send_video_info(bot: Bot, ev: MessageEvent, data: VideoInfo):
    """发送视频信息"""

    try:
        stream = data.stream
        msg = Message(
            [
                MessageSegment.text(data.title),
                MessageSegment.image(data.pic),
                MessageSegment.text(f'https://www.bilibili.com/video/{data.bvid}/'),
            ]
        )
        if stream.skip_download and stream.skip_download_msg is not None:
            msg.append(MessageSegment.text(f'\r{stream.skip_download_msg}'))

        logger.debug(f'开始发送消息: {data.bvid} - {msg}')
        await bot.send(ev, msg)

        file_path = None
        cache_file_path = get_cache_file_path(data.bvid)
        if cache_file_path.exists():
            file_path = cache_file_path
        elif not stream.skip_download:
            assert stream.url is not None
            file_path = await download(data.bvid, stream.url)

        if file_path is None:
            return

        try:
            async with _send_video_lock(data.bvid):
                t0 = time.monotonic()

                napcat_file_path = get_napcat_cache_file_path(file_path)
                if napcat_file_path is not None:
                    logger.debug(f'{TAG} 使用缓存映射跳过 WS 流式上传')
                    await bot.send(ev, MessageSegment.video(str(napcat_file_path)))
                else:
                    logger.debug(f'{TAG} 未配置缓存映射，使用 WS 流式上传')
                    uploaded_file_path = await upload_file_stream(
                        bot, file_path, options=UploadOptions(chunk_size=1024 * 1024)
                    )
                    await bot.send(ev, MessageSegment.video(uploaded_file_path))

                elapsed = time.monotonic() - t0
                speed = bytes_to_mibps(file_path.stat().st_size, elapsed)
                logger.info(f'{TAG} {data.bvid} 视频发送完成，耗时 {elapsed:.1f}s, 速度 {speed:.2f} MiB/s')
        except Exception as e:
            logger.error(f'视频发送失败: {data.bvid} - {e}')
    except Exception as e:
        logger.error(f'消息发送失败: {data.bvid} - {e}')
