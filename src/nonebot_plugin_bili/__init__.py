"""B 站视频解析与直播开播提醒插件。"""

from importlib.metadata import PackageNotFoundError, version

from nonebot import require, get_driver
from nonebot.plugin import PluginMetadata

require('nonebot_plugin_apscheduler')

from .config import Config  # noqa: E402

try:
    __version__ = version('nonebot-plugin-bili')
except PackageNotFoundError:  # pragma: no cover - 源码未安装时的回退
    __version__ = '0.1.0'

__plugin_meta__ = PluginMetadata(
    name='哔哩哔哩',
    description='B 站视频解析与直播开播提醒',
    usage=(
        '发送 B 站视频链接（BV / b23.tv / 分享卡片）自动解析并尝试下载发送；\n'
        '超级管理员私聊：订阅直播 / 取消订阅直播 / 直播订阅列表。\n'
        '可选配置 BILI_SEND、BILI_NAPCAT_CACHE_DIR、BILI_GROUP_BLACKLIST 等。\n'
        '请遵守 B 站服务条款与当地法律，勿未授权传播他人内容。'
    ),
    type='application',
    homepage='https://github.com/qianxuu/nonebot-plugin-bili',
    config=Config,
    supported_adapters={'~onebot.v11'},
    extra={
        'author': 'qianxu',
        'version': __version__,
        'license': 'MIT',
    },
)

from . import live as _live  # noqa: E402, F401
from . import video as _video  # noqa: E402, F401


@get_driver().on_startup
async def _on_startup() -> None:
    from nonebot import logger

    from .database import ensure_db

    ensure_db()
    logger.debug('[哔哩哔哩] 插件已启动')


@get_driver().on_shutdown
async def _on_shutdown() -> None:
    from .client import close_client
    from .live_ws import stop_all_ws

    stop_all_ws()
    await close_client()
