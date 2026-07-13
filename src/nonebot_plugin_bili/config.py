from pathlib import Path

from nonebot import get_plugin_config
from pydantic import Field, BaseModel, field_validator


class Config(BaseModel):
    """B 站插件配置（字段名对应 .env 中的 BILI_*，大小写不敏感）"""

    bili_napcat_cache_dir: Path | None = None
    bili_group_blacklist: set[int] = Field(default_factory=set)
    # 超过该大小的视频跳过下载（MiB）
    bili_max_video_size_mib: float = 50
    # 同一 bvid 在同一群的冷却秒数
    bili_group_cd_seconds: int = 60
    # 本地缓存保留时长（小时）；下载前清理过期文件
    bili_cache_retention_hours: float = 24
    # 直播状态轮询间隔（秒）
    bili_live_poll_interval: int = 15

    @field_validator('bili_napcat_cache_dir', mode='before')
    @classmethod
    def _empty_path_to_none(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @field_validator('bili_max_video_size_mib')
    @classmethod
    def _positive_max_video_size(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('bili_max_video_size_mib 必须大于 0')
        return value

    @field_validator('bili_group_cd_seconds')
    @classmethod
    def _non_negative_cd(cls, value: int) -> int:
        if value < 0:
            raise ValueError('bili_group_cd_seconds 不能为负数')
        return value

    @field_validator('bili_cache_retention_hours')
    @classmethod
    def _positive_retention(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('bili_cache_retention_hours 必须大于 0')
        return value

    @field_validator('bili_live_poll_interval')
    @classmethod
    def _positive_poll_interval(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('bili_live_poll_interval 必须大于 0')
        return value


_SETTINGS = get_plugin_config(Config)
BILI_NAPCAT_CACHE_DIR = _SETTINGS.bili_napcat_cache_dir
BILI_GROUP_BLACKLIST = _SETTINGS.bili_group_blacklist
BILI_MAX_VIDEO_SIZE = int(_SETTINGS.bili_max_video_size_mib * 1024 * 1024)
BILI_GROUP_CD_SECONDS = _SETTINGS.bili_group_cd_seconds
BILI_CACHE_RETENTION_SECONDS = int(_SETTINGS.bili_cache_retention_hours * 3600)
BILI_LIVE_POLL_INTERVAL = _SETTINGS.bili_live_poll_interval


def get_napcat_cache_file_path(file_path: Path) -> Path | None:
    """将本地缓存文件路径映射为 NapCat 容器内路径，未配置则返回 None"""

    if BILI_NAPCAT_CACHE_DIR is None:
        return None
    return BILI_NAPCAT_CACHE_DIR / file_path.name
