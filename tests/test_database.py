from pathlib import Path

from nonebot_plugin_bili import database as db


def _use_tmp_db(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(db, 'DB_FILE', tmp_path / 'bili.db')
    db.init_db()


def test_sub_crud(tmp_path: Path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert db.add_sub(1, 100, 'u1', 't1') is True
    assert db.add_sub(1, 100, 'u1', 't1') is True  # ignore duplicate
    assert db.get_all_sub_uids() == [1]
    assert db.get_sub_groups(1) == [100]
    assert db.get_all_subs() == [{'uid': 1, 'group_id': 100, 'uname': 'u1'}]
    assert db.get_sub_title(1) == 't1'
    db.set_sub_title(1, 't2')
    assert db.get_sub_title(1) == 't2'
    assert db.remove_sub(1, 100) is True
    assert db.remove_sub(1, 100) is False
    assert db.get_all_sub_uids() == []


def test_session_lifecycle(tmp_path: Path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    db.insert_session(9, 1000, 'title', 'cover', 55, 'name')
    active = db.get_active_session(9)
    assert active is not None
    assert active['notified_start'] == 0
    db.mark_start_notified(9, 1000)
    db.update_session_watched(9, 12)
    db.update_session_max_online(9, 3)
    db.update_session_max_online(9, 5)
    active = db.get_active_session(9)
    assert active is not None
    assert active['notified_start'] == 1
    assert active['watched'] == 12
    assert active['max_online'] == 5
    db.mark_stop_notified(9, 1000)
    assert db.get_active_session(9) is None
    stopped = db.get_last_stopped_session(9)
    assert stopped is not None
    assert stopped['notified_stop'] == 1


def test_ensure_db_idempotent(tmp_path: Path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    db.ensure_db()
    db.ensure_db()
    assert (tmp_path / 'bili.db').exists()
