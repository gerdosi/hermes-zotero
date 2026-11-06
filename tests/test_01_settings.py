from dataclasses import fields

from zotcore.settings import DEFAULTS, Settings


def getter(values):
    return lambda key, default=None: values.get(key, default)


def test_defaults():
    s = Settings.from_getter(getter({}))
    assert s.zotero_data_dir == ""
    assert s.markdown_path == ""
    assert s.libraries == ("user",)
    assert s.coverage_strong_min == 8
    assert s.coverage_recent_min == 2
    assert s.coverage_recent_years == 5
    assert s.sync_batch_items == 200
    assert s.sync_tool_budget_seconds == 30
    assert s.read_max_chars_default == 4000
    assert s.read_max_chars_cap == 12000
    assert s.warnings == ()


def test_defaults_table_matches_dataclass():
    assert set(DEFAULTS) == {f.name for f in fields(Settings)} - {"warnings"}


def test_wrong_type_falls_back_with_warning():
    s = Settings.from_getter(getter({"sync_batch_items": "lots", "zotero_data_dir": 5}))
    assert s.sync_batch_items == 200
    assert s.zotero_data_dir == ""
    assert any("sync_batch_items" in w for w in s.warnings)
    assert any("zotero_data_dir" in w for w in s.warnings)


def test_bool_is_not_accepted_as_int():
    s = Settings.from_getter(getter({"sync_batch_items": True}))
    assert s.sync_batch_items == 200
    assert s.warnings


def test_clamping():
    s = Settings.from_getter(getter({"sync_tool_budget_seconds": 600, "read_max_chars_default": 50000}))
    assert s.sync_tool_budget_seconds == 60
    assert s.read_max_chars_default == 12000  # never above read_max_chars_cap
    assert len(s.warnings) >= 2


def test_libraries_accepts_yaml_ints_and_drops_junk():
    s = Settings.from_getter(getter({"libraries": ["user", 4805701, "123", "bad", None]}))
    assert s.libraries == ("user", "4805701", "123")
    assert any("libraries" in w for w in s.warnings)


def test_empty_libraries_falls_back_to_user():
    s = Settings.from_getter(getter({"libraries": []}))
    assert s.libraries == ("user",)
    assert s.warnings


def test_getter_that_raises_gives_defaults():
    def boom(key, default=None):
        raise RuntimeError("config unreadable")
    s = Settings.from_getter(boom)
    assert s.sync_batch_items == 200
    assert s.warnings


def test_settings_is_immutable():
    s = Settings()
    try:
        s.sync_batch_items = 5
    except Exception:
        return
    raise AssertionError("Settings must be frozen")
