"""视频下载"""

import math
import time
import asyncio
from pathlib import Path

import aiohttp
from nonebot import logger

from .wbi import HEADERS
from .utils import KeyedLock, bytes_to_mib, bytes_to_mibps
from .config import BILI_CACHE_RETENTION_SECONDS

_TAG = '[哔哩下载]'
_CACHE_DIR = Path('cache/bili')
_DOWNLOAD_LOCK = KeyedLock()
_WRITE_LOCK = asyncio.Lock()

_CHUNK_SIZE = 2 * 1024 * 1024
_MAX_CHUNKS = 8
_CHUNK_RETRIES = 3
_RETRY_INTERVAL = 1


def _calculate_chunk_count(content_length: int) -> int:
    """根据文件大小计算分片数，每个分片 2MB，最多 8 个分片"""

    if content_length <= 0:
        raise ValueError('content_length 必须大于 0')
    return min(math.ceil(content_length / _CHUNK_SIZE), _MAX_CHUNKS)


def get_cache_file_path(bvid: str) -> Path:
    """返回视频缓存文件路径"""

    return _CACHE_DIR / f'{bvid}.mp4'


def _prune_cache(cache_dir: Path, *, now: float | None = None) -> None:
    """清理过期缓存文件；单个文件删除失败时记录并继续。"""

    if not cache_dir.is_dir():
        return

    threshold = (now if now is not None else time.time()) - BILI_CACHE_RETENTION_SECONDS
    for path in cache_dir.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < threshold:
                path.unlink()
        except OSError as e:
            logger.warning(f'{_TAG} 清理缓存失败: {path.name} - {e}')


async def _download_chunk(session: aiohttp.ClientSession, url: str, start: int, end: int) -> tuple[int, bytes]:
    """下载文件的一个分片，返回起始位置和数据"""

    headers = {**HEADERS, 'Range': f'bytes={start}-{end}'}
    retry_exceptions = (
        aiohttp.ClientPayloadError,
        aiohttp.ServerTimeoutError,
        aiohttp.ServerDisconnectedError,
    )
    for attempt in range(1, _CHUNK_RETRIES + 1):
        try:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                chunks = []
                async for chunk in resp.content.iter_chunked(65536):
                    chunks.append(chunk)
            data = b''.join(chunks)
            return start, data
        except retry_exceptions as e:
            if attempt == _CHUNK_RETRIES:
                raise
            logger.warning(f'{_TAG} 分片 {start}-{end} 第 {attempt} 次失败: {e}，准备重试')
            await asyncio.sleep(_RETRY_INTERVAL * attempt)
    raise RuntimeError(f'分片下载失败: {start}-{end}')


async def download(bvid: str, url: str, size: int) -> Path | None:
    """下载视频。size 来自 playurl API 的 durl.size，用于分片下载。"""

    async with _DOWNLOAD_LOCK(bvid):
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        file_path = get_cache_file_path(bvid)
        if file_path.exists():
            logger.info(f'{_TAG} {bvid} 已缓存，跳过下载')
            return file_path

        _prune_cache(_CACHE_DIR)

        if size <= 0:
            logger.error(f'{_TAG} {bvid} 无效文件大小: {size}，跳过下载')
            return None

        content_length = size
        num_chunks = _calculate_chunk_count(content_length)
        logger.info(f'{_TAG} {bvid} 开始: {bytes_to_mib(content_length):.2f} MiB, {num_chunks} 连接')
        t_start = time.monotonic()
        temp_path = file_path.with_suffix('.tmp')

        try:
            chunk_size = content_length // num_chunks
            ranges = []
            for i in range(num_chunks):
                start = i * chunk_size
                end = (i + 1) * chunk_size - 1 if i < num_chunks - 1 else content_length - 1
                ranges.append((start, end))

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                connector=aiohttp.TCPConnector(limit_per_host=num_chunks),
            ) as session:
                tasks = [_download_chunk(session, url, start, end) for start, end in ranges]
                chunks = await asyncio.gather(*tasks)

            for (_start, data), (range_start, range_end) in zip(chunks, ranges, strict=True):
                expected_size = range_end - range_start + 1
                if len(data) != expected_size:
                    raise ValueError(f'分片数据大小不匹配: 期望 {expected_size} 字节, 实际 {len(data)} 字节')

            total_size = sum(len(data) for _, data in chunks)
            if total_size != content_length:
                raise ValueError(f'总文件大小不匹配: 期望 {content_length} 字节, 实际 {total_size} 字节')

            async with _WRITE_LOCK:
                with temp_path.open('wb') as file:
                    file.truncate(content_length)
                    for start, data in chunks:
                        file.seek(start)
                        file.write(data)
                temp_path.rename(file_path)

            t_total = time.monotonic() - t_start
            speed = bytes_to_mibps(content_length, t_total)
            logger.info(
                f'{_TAG} {bvid} 完成: {bytes_to_mib(content_length):.2f} MiB, '
                f'耗时 {t_total:.1f}s, 总速度 {speed:.2f} MiB/s'
            )
            return file_path
        except Exception as e:
            logger.error(f'{_TAG} 视频下载失败: {bvid} - {e}')
            temp_path.unlink(missing_ok=True)
            file_path.unlink(missing_ok=True)
            return None
