"""NapCat Stream API"""

import base64
import hashlib
from uuid import uuid4
from pathlib import Path
from dataclasses import dataclass

from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Bot

from .utils import bytes_to_mib

DEFAULT_UPLOAD_CHUNK_SIZE = 64 * 1024
DEFAULT_FILE_RETENTION_MS = 30 * 1000


@dataclass(slots=True, frozen=True)
class UploadOptions:
    chunk_size: int = DEFAULT_UPLOAD_CHUNK_SIZE
    file_retention_ms: int = DEFAULT_FILE_RETENTION_MS


DEFAULT_UPLOAD_OPTIONS = UploadOptions()


def _calculate_file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


async def upload_file_stream(
    bot: Bot,
    file_path: Path,
    *,
    options: UploadOptions = DEFAULT_UPLOAD_OPTIONS,
) -> str:
    file_size = file_path.stat().st_size
    chunk_size = options.chunk_size
    total_chunks = max(1, (file_size + chunk_size - 1) // chunk_size)
    expected_sha256 = _calculate_file_sha256(file_path)
    stream_id = str(uuid4())

    logger.info(f'[上传] 开始流式上传 {file_path.name}: {bytes_to_mib(file_size):.2f} MiB, {total_chunks} 分片')

    with file_path.open('rb') as file:
        for chunk_index in range(total_chunks):
            chunk_data = file.read(chunk_size)
            if not chunk_data:
                break

            await bot.call_api(
                'upload_file_stream',
                stream_id=stream_id,
                chunk_data=base64.b64encode(chunk_data).decode('ascii'),
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                file_size=file_size,
                expected_sha256=expected_sha256,
                filename=file_path.name,
                file_retention=options.file_retention_ms,
            )

    result = await bot.call_api('upload_file_stream', stream_id=stream_id, is_complete=True)
    if not (uploaded_file_path := result.get('file_path')):
        raise RuntimeError(f'[上传] 流式上传失败: {result}')
    return uploaded_file_path
