import sqlite3
from typing import TypedDict
from pathlib import Path
from contextlib import contextmanager

from nonebot import logger

DATA_DIR = Path('data/bili')
DB_FILE = DATA_DIR / 'bili.db'


class LiveSub(TypedDict):
    uid: int
    group_id: int
    uname: str


class LiveSession(TypedDict):
    uid: int
    live_time: int
    title: str
    cover: str
    room_id: int
    uname: str
    notified_start: int
    notified_stop: int
    watched: int
    max_online: int


def init_db():
    """初始化数据库"""

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _conn() as conn:
        cursor = conn.cursor()

        # 订阅表：记录哪些群订阅了哪些主播
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_sub (
            uid INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            uname TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            UNIQUE(uid, group_id)
        )
        """)

        # 直播会话表：记录每次开播的状态和通知推送情况
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_session (
            uid INTEGER NOT NULL,
            live_time INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            cover TEXT NOT NULL DEFAULT '',
            room_id INTEGER NOT NULL DEFAULT 0,
            uname TEXT NOT NULL DEFAULT '',
            notified_start INTEGER NOT NULL DEFAULT 0,
            notified_stop INTEGER NOT NULL DEFAULT 0,
            watched INTEGER NOT NULL DEFAULT 0,
            max_online INTEGER NOT NULL DEFAULT 0,
            UNIQUE(uid, live_time)
        )
        """)

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sub_uid ON live_sub(uid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_active ON live_session(uid, notified_stop)')
        conn.commit()

    logger.debug('bili 数据库初始化完成')


@contextmanager
def _conn():
    """获取数据库连接"""

    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
    finally:
        conn.close()


# -------- 订阅管理 --------


def add_sub(uid: int, group_id: int, uname: str = '', title: str = '') -> bool:
    """添加订阅"""

    try:
        with _conn() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO live_sub (uid, group_id, uname, title) VALUES (?, ?, ?, ?)',
                (uid, group_id, uname, title),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f'添加订阅失败: {e}')
        return False


def remove_sub(uid: int, group_id: int) -> bool:
    """移除订阅"""

    try:
        with _conn() as conn:
            cursor = conn.execute(
                'DELETE FROM live_sub WHERE uid = ? AND group_id = ?',
                (uid, group_id),
            )
            affected = cursor.rowcount
            conn.commit()
        return affected > 0
    except Exception as e:
        logger.error(f'移除订阅失败: {e}')
        return False


def get_all_sub_uids() -> list[int]:
    """获取所有订阅的 uid"""

    with _conn() as conn:
        rows = conn.execute('SELECT DISTINCT uid FROM live_sub').fetchall()
    return [r[0] for r in rows]


def get_sub_groups(uid: int) -> list[int]:
    """获取订阅了某主播的所有群"""

    with _conn() as conn:
        rows = conn.execute('SELECT group_id FROM live_sub WHERE uid = ?', (uid,)).fetchall()
    return [r[0] for r in rows]


def get_all_subs() -> list[LiveSub]:
    """获取所有订阅记录，按主播分组"""

    with _conn() as conn:
        rows = conn.execute(
            'SELECT uid, group_id, uname FROM live_sub ORDER BY uid',
        ).fetchall()
    return [{'uid': r[0], 'group_id': r[1], 'uname': r[2]} for r in rows]


# -------- 直播会话管理 --------


def insert_session(uid: int, live_time: int, title: str, cover: str, room_id: int, uname: str):
    """插入直播会话"""

    with _conn() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO live_session'
            ' (uid, live_time, title, cover, room_id, uname) VALUES (?, ?, ?, ?, ?, ?)',
            (uid, live_time, title, cover, room_id, uname),
        )
        conn.commit()


def get_active_session(uid: int) -> LiveSession | None:
    """获取某主播最新未完成下播通知的会话"""

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT uid, live_time, title, cover, room_id, uname, notified_start, notified_stop, watched, max_online
            FROM live_session
            WHERE uid = ? AND notified_stop = 0
            ORDER BY live_time DESC LIMIT 1
            """,
            (uid,),
        ).fetchone()
    if row is None:
        return None
    return {
        'uid': row[0],
        'live_time': row[1],
        'title': row[2],
        'cover': row[3],
        'room_id': row[4],
        'uname': row[5],
        'notified_start': row[6],
        'notified_stop': row[7],
        'watched': row[8],
        'max_online': row[9],
    }


def get_last_stopped_session(uid: int) -> LiveSession | None:
    """获取某主播最近一条已结束（已推送下播通知）的会话"""
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT uid, live_time, title, cover, room_id, uname, notified_start, notified_stop, watched, max_online
            FROM live_session
            WHERE uid = ? AND notified_stop = 1
            ORDER BY live_time DESC LIMIT 1
            """,
            (uid,),
        ).fetchone()
    if row is None:
        return None
    return {
        'uid': row[0],
        'live_time': row[1],
        'title': row[2],
        'cover': row[3],
        'room_id': row[4],
        'uname': row[5],
        'notified_start': row[6],
        'notified_stop': row[7],
        'watched': row[8],
        'max_online': row[9],
    }


def mark_start_notified(uid: int, live_time: int):
    """标记开播通知已推送"""

    with _conn() as conn:
        conn.execute('UPDATE live_session SET notified_start = 1 WHERE uid = ? AND live_time = ?', (uid, live_time))
        conn.commit()


def mark_stop_notified(uid: int, live_time: int):
    """标记下播通知已推送"""

    with _conn() as conn:
        conn.execute('UPDATE live_session SET notified_stop = 1 WHERE uid = ? AND live_time = ?', (uid, live_time))
        conn.commit()


def update_session_watched(uid: int, watched: int):
    """更新活跃会话的观看人数"""

    with _conn() as conn:
        conn.execute('UPDATE live_session SET watched = ? WHERE uid = ? AND notified_stop = 0', (watched, uid))
        conn.commit()


def update_session_max_online(uid: int, online: int):
    """更新活跃会话的最高同接"""

    with _conn() as conn:
        conn.execute(
            'UPDATE live_session SET max_online = MAX(max_online, ?) WHERE uid = ? AND notified_stop = 0',
            (online, uid),
        )
        conn.commit()


def get_sub_title(uid: int) -> str:
    """获取订阅表中某主播的标题"""

    with _conn() as conn:
        row = conn.execute(
            'SELECT title FROM live_sub WHERE uid = ? LIMIT 1',
            (uid,),
        ).fetchone()
    return row[0] if row else ''


def set_sub_title(uid: int, new_title: str):
    """更新订阅表中某主播的标题"""

    with _conn() as conn:
        conn.execute(
            'UPDATE live_sub SET title = ? WHERE uid = ?',
            (new_title, uid),
        )
        conn.commit()


def ensure_db() -> None:
    """确保数据库已初始化（可重复调用）。"""

    init_db()
