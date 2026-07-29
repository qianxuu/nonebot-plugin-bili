from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from nonebot import logger

from .utils import bytes_to_mib
from .client import post, request
from .config import BILI_MAX_VIDEO_SIZE
from .download import get_cache_file_path

TAG = '[哔哩 API]'


@dataclass
class VideoStreamInfo:
    """视频流信息"""

    skip_download: bool = True
    skip_download_msg: str | None = None
    url: str | None = None
    size: int | None = None


@dataclass
class VideoInfo:
    """视频信息"""

    bvid: str
    pic: str
    title: str
    owner_name: str
    pubdate: int
    duration: int
    view: int
    like: int
    coin: int
    favorite: int
    share: int
    stream: VideoStreamInfo


# -------- 视频 API --------


async def get_video_info(bvid: str) -> VideoInfo | None:
    """获取视频信息"""

    try:
        data = await request('https://api.bilibili.com/x/web-interface/wbi/view', {'bvid': bvid})
        if data.get('code') != 0:
            raise Exception(data.get('message'))

        logger.info(f'视频信息获取成功: {bvid}')

        data = data['data']
        stat = data['stat']

        cache_file_path = get_cache_file_path(bvid)
        if cache_file_path.exists():
            logger.info(f'视频已缓存，跳过获取视频流信息: {bvid}')
            stream = VideoStreamInfo(skip_download=True)
        else:
            stream = await get_video_stream_info(bvid, data['cid'])

        return VideoInfo(
            bvid=bvid,
            pic=data['pic'],
            title=data['title'],
            owner_name=data['owner']['name'],
            pubdate=data['pubdate'],
            duration=data['duration'],
            view=stat['view'],
            like=stat['like'],
            coin=stat['coin'],
            favorite=stat['favorite'],
            share=stat['share'],
            stream=stream,
        )
    except Exception as e:
        logger.error(f'视频信息获取失败: {bvid} - {e}')
        return None


async def get_video_stream_info(bvid: str, cid: int) -> VideoStreamInfo:
    """获取视频流信息"""

    try:
        data = await request('https://api.bilibili.com/x/player/wbi/playurl', {'bvid': bvid, 'cid': cid, 'qn': 64})

        code = data.get('code')
        if code == 87008:
            logger.info(f'充电专属: {bvid}')
            return VideoStreamInfo(skip_download_msg='充电专属视频，请前往哔哩哔哩观看')
        if code != 0:
            logger.error(f'视频流信息获取失败: {bvid} - {data}')
            return VideoStreamInfo(skip_download_msg='请前往哔哩哔哩观看')

        payload = data.get('data') or {}
        durls = payload.get('durl') or []
        if not durls:
            logger.error(f'视频流信息获取失败: {bvid} - 无 durl，返回字段: {sorted(payload.keys())}')
            return VideoStreamInfo(skip_download_msg='请前往哔哩哔哩观看')

        durl = durls[0]
        size = durl.get('size', 0)

        if size > BILI_MAX_VIDEO_SIZE:
            logger.info(f'视频过大: {bvid} - {bytes_to_mib(size):.2f} MiB')
            return VideoStreamInfo(skip_download_msg='视频较大，请前往哔哩哔哩观看')

        candidates = [durl.get('url'), *(durl.get('backup_url') or [])]
        valid_url = next((u for u in candidates if u and not _is_pcdn(u)), None)
        if valid_url is None:
            logger.error(f'视频流信息获取失败: {bvid} - 无有效流地址')
            return VideoStreamInfo(skip_download_msg='请前往哔哩哔哩观看')

        logger.info(f'视频流信息获取成功: {bvid} - {bytes_to_mib(size):.2f} MiB')
        return VideoStreamInfo(skip_download=False, url=valid_url, size=size)
    except Exception as e:
        logger.error(f'视频流信息获取失败: {bvid} - {e}')
        return VideoStreamInfo(skip_download_msg='请前往哔哩哔哩观看')


def _is_pcdn(url: str) -> bool:
    """判断视频流地址是否为 PCDN / MCDN。"""

    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        os_value = (qs.get('os', [''])[0] or '').lower()

        return os_value in {'bcache', 'mcdn'}
    except Exception:
        return False


# -------- 直播 API --------


async def fetch_live_status(uids: list[int]) -> dict | None:
    """获取主播直播状态"""

    try:
        data = await post('https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids', json={'uids': uids})
        if data.get('code') != 0:
            logger.error(f'{TAG} 获取主播直播状态失败: {data}')
            return None

        payload = data.get('data', {})
        if payload is None:
            return {}
        if isinstance(payload, list) and not payload:
            return {}
        if not isinstance(payload, dict):
            logger.error(f'{TAG} 获取主播直播状态失败: data 字段类型异常: {type(payload).__name__}')
            return None

        return payload
    except Exception as e:
        logger.error(f'{TAG} 获取主播直播状态失败: {e}')
        return None


async def fetch_danmu_info(room_id: int) -> dict | None:
    """获取直播间信息流认证密钥和服务器列表"""

    try:
        data = await request(
            'https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo',
            {'id': room_id, 'type': 0},
        )
        if data.get('code') != 0:
            logger.error(f'{TAG} 获取认证密钥失败: room={room_id}, {data}')
            return None
        return data.get('data')
    except Exception as e:
        logger.error(f'{TAG} 获取认证密钥失败: room={room_id}, {e}')
        return None
