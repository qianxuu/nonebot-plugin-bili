from pathlib import Path

from nonebot_plugin_bili import config as config_mod
from nonebot_plugin_bili.config import Config


def test_empty_path_and_defaults():
    cfg = Config.model_validate(
        {
            'bili_napcat_cache_dir': '  ',
            'bili_group_blacklist': ['1', 2],
        }
    )
    assert cfg.bili_napcat_cache_dir is None
    assert cfg.bili_group_blacklist == {1, 2}
    assert cfg.bili_send == {'cover', 'video'}
    assert cfg.bili_max_video_size_mib == 50
    assert cfg.bili_group_cd_seconds == 60
    assert cfg.bili_cache_retention_hours == 24
    assert cfg.bili_live_poll_interval == 15


def test_bili_send_json_array_and_aliases():
    cfg = Config.model_validate({'bili_send': '["cover"]'})
    assert cfg.bili_send == {'cover'}

    cfg = Config.model_validate({'bili_send': ['VIDEO', ' Cover ']})
    assert cfg.bili_send == {'video', 'cover'}

    cfg = Config.model_validate({'bili_send': 'video,cover'})
    assert cfg.bili_send == {'video', 'cover'}

    cfg = Config.model_validate({'bili_send': []})
    assert cfg.bili_send == set()


def test_validators_reject_invalid_values():
    for field, value in [
        ('bili_max_video_size_mib', 0),
        ('bili_group_cd_seconds', -1),
        ('bili_cache_retention_hours', 0),
        ('bili_live_poll_interval', 0),
        ('bili_send', ['audio']),
        ('bili_send', 'not-json'),
    ]:
        try:
            Config.model_validate({field: value})
            raise AssertionError(f'expected validation error for {field}')
        except Exception:
            pass


def test_get_napcat_cache_file_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_mod, 'BILI_NAPCAT_CACHE_DIR', None)
    assert config_mod.get_napcat_cache_file_path(tmp_path / 'a.mp4') is None

    monkeypatch.setattr(config_mod, 'BILI_NAPCAT_CACHE_DIR', Path('/app/temp'))
    assert config_mod.get_napcat_cache_file_path(tmp_path / 'a.mp4') == Path('/app/temp/a.mp4')
