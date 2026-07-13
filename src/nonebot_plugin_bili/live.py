import re
import time

from nonebot import logger, get_bot, on_command
from nonebot.permission import SUPERUSER
from nonebot_plugin_apscheduler import scheduler
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment, PrivateMessageEvent

from .api import fetch_live_status
from .config import BILI_LIVE_POLL_INTERVAL
from .live_ws import stop_ws, start_ws
from .database import (
    LiveSession,
    add_sub,
    remove_sub,
    get_all_subs,
    get_sub_title,
    set_sub_title,
    get_sub_groups,
    insert_session,
    get_all_sub_uids,
    get_active_session,
    mark_stop_notified,
    mark_start_notified,
    get_last_stopped_session,
)

TAG = '[哔哩直播]'


async def send_live_start(uid: int, session: LiveSession):
    """推送开播通知到所有订阅群"""

    groups = get_sub_groups(uid)
    if not groups:
        return

    uname = session['uname']
    title = session['title']
    cover = session['cover']
    room_id = session['room_id']

    since_last = ''
    last_session = get_last_stopped_session(uid)
    if last_session:
        diff_sec = session['live_time'] - last_session['live_time']
        if diff_sec >= 86400:
            since_last = f'{diff_sec // 86400} 天'
        elif diff_sec >= 3600:
            since_last = f'{diff_sec // 3600} 小时'
        elif diff_sec >= 60:
            since_last = f'{diff_sec // 60} 分'

    msg = Message(
        [
            MessageSegment.text(f'{uname} 开播了：\n{title}'),
            MessageSegment.image(cover),
            MessageSegment.text(
                (f'距上次开播：{since_last}\n' if since_last else '') + f'https://live.bilibili.com/{room_id}/'
            ),
        ]
    )

    bot = get_bot()
    for group_id in groups:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
            logger.info(f'{TAG} 开播通知已推送: {uname} -> {group_id}')
        except Exception as e:
            logger.error(f'{TAG} 开播通知推送失败: {uname} -> {group_id} - {e}')


async def send_live_stop(uid: int, session: LiveSession):
    """推送下播通知到所有订阅群"""

    groups = get_sub_groups(uid)
    if not groups:
        return

    uname = session['uname']
    watched = session['watched']
    max_online = session['max_online']

    duration_sec = int(time.time()) - session['live_time']
    if duration_sec > 0:
        hours, remainder = divmod(duration_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = f'{hours} 时 {minutes} 分' if hours > 0 else f'{minutes} 分 {seconds} 秒'
    else:
        duration_str = '未知'

    bot = get_bot()
    for group_id in groups:
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=f'{uname} 下播了：\n持续时长：{duration_str}\n观看人次：{watched}\n最高同接：{max_online}',
            )
            logger.info(f'{TAG} 下播通知已推送: {uname} -> {group_id}')
        except Exception as e:
            logger.error(f'{TAG} 下播通知推送失败: {uname} -> {group_id} - {e}')


async def send_title_change(uid: int, uname: str, room_id: int, old_title: str, new_title: str):
    """推送直播间标题变更通知到所有订阅群"""

    groups = get_sub_groups(uid)
    if not groups:
        return

    msg = f'{uname} 直播间标题变更：\n-\t{old_title}\n+\t{new_title}\nhttps://live.bilibili.com/{room_id}/'

    bot = get_bot()
    for group_id in groups:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
            logger.info(f'{TAG} 标题变更通知已推送: {uname} -> {group_id}')
        except Exception as e:
            logger.error(f'{TAG} 标题变更通知推送失败: {uname} -> {group_id} - {e}')


@scheduler.scheduled_job('interval', seconds=BILI_LIVE_POLL_INTERVAL, id='bili_live_poll')
async def poll_live_status():
    """定时轮询直播状态"""

    uids = get_all_sub_uids()
    if not uids:
        return

    logger.debug(f'{TAG} 检查 {len(uids)} 个主播状态')
    status_data = await fetch_live_status(uids)
    if status_data is None:
        return

    for uid in uids:
        uid_str = str(uid)
        info = status_data.get(uid_str)
        if info is None:
            logger.debug(f'{TAG} uid={uid} 未返回数据')
            continue

        live_status = info.get('live_status', 0)
        live_time = info.get('live_time', 0)
        uname = info.get('uname', '')
        title = info.get('title', '')
        room_id = info.get('room_id', 0)
        cover = info.get('cover_from_user', '') or info.get('keyframe', '')

        old_title = get_sub_title(uid)
        if old_title != title:
            logger.info(f'{TAG} 检测到标题变更: {uname} (uid: {uid}) "{old_title}" -> "{title}"')
            await send_title_change(uid, uname, room_id, old_title, title)
            set_sub_title(uid, title)

        if live_status == 1:
            old_session = get_active_session(uid)
            if old_session and old_session['live_time'] != live_time and old_session['notified_start']:
                logger.info(f'{TAG} 补发下播通知: {uname} (uid: {uid})')
                stop_ws(uid)
                await send_live_stop(uid, old_session)
                mark_stop_notified(uid, old_session['live_time'])

            insert_session(uid, live_time, title, cover, room_id, uname)
            start_ws(uid, room_id)
            session = get_active_session(uid)
            if session and not session['notified_start']:
                logger.info(f'{TAG} 检测到开播: {uname} (uid: {uid})')
                await send_live_start(uid, session)
                mark_start_notified(uid, live_time)
        else:
            session = get_active_session(uid)
            if session and session['notified_start']:
                logger.info(f'{TAG} 检测到下播: {uname} (uid: {uid})')
                stop_ws(uid)
                await send_live_stop(uid, session)
                mark_stop_notified(uid, session['live_time'])


@on_command('订阅直播', permission=SUPERUSER).handle()
async def handle_subscribe(bot: Bot, ev: PrivateMessageEvent):
    """订阅直播通知"""

    match = re.search(r'(\d+)\s+(\d+)', ev.get_plaintext())
    if not match:
        await bot.send(ev, '格式: 订阅直播 <uid> <群号>')
        return

    uid = int(match.group(1))
    group_id = int(match.group(2))

    status = await fetch_live_status([uid])
    if status is None or str(uid) not in status:
        await bot.send(ev, f'未找到主播 uid={uid}，请检查 uid 是否正确')
        return

    info = status[str(uid)]
    uname = info.get('uname', str(uid))
    title = info.get('title', '')

    if add_sub(uid, group_id, uname, title):
        await bot.send(ev, f'已订阅 {uname} (uid: {uid}) -> {group_id}')
    else:
        await bot.send(ev, '订阅失败，请稍后重试')


@on_command('取消订阅直播', permission=SUPERUSER).handle()
async def handle_unsubscribe(bot: Bot, ev: PrivateMessageEvent):
    """取消订阅直播通知"""

    match = re.search(r'(\d+)\s+(\d+)', ev.get_plaintext())
    if not match:
        await bot.send(ev, '格式: 取消订阅直播 <uid> <群号>')
        return

    uid = int(match.group(1))
    group_id = int(match.group(2))

    if remove_sub(uid, group_id):
        if not get_sub_groups(uid):
            session = get_active_session(uid)
            if session:
                stop_ws(uid)
                mark_stop_notified(uid, session['live_time'])
        await bot.send(ev, f'已取消订阅 {uid} -> {group_id}')
    else:
        await bot.send(ev, f'未订阅 {uid} -> {group_id}')


@on_command('直播订阅列表', permission=SUPERUSER).handle()
async def handle_sub_list(bot: Bot, ev: PrivateMessageEvent):
    """查看所有直播订阅"""

    subs = get_all_subs()
    if not subs:
        await bot.send(ev, '当前没有任何订阅主播')
        return

    grouped: dict[int, dict] = {}
    for sub in subs:
        uid = sub['uid']
        if uid not in grouped:
            grouped[uid] = {'uname': sub['uname'] or str(uid), 'groups': []}
        grouped[uid]['groups'].append(sub['group_id'])

    lines = [f'共订阅 {len(grouped)} 个主播：']
    for i, (uid, info) in enumerate(grouped.items(), 1):
        group_str = ', '.join(str(g) for g in info['groups'])
        lines.append(f'{i}. {info["uname"]} (uid: {uid}) -> {group_str}')
    await bot.send(ev, '\n'.join(lines))
