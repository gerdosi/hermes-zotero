import json
from pathlib import Path

from zotcore import tools
from zotcore.datadir import parse_prefs, profile_roots, resolve_data_dir
from zotcore.settings import Settings


def make_data_dir(path: Path, storage=True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "zotero.sqlite").write_bytes(b"")
    if storage:
        (path / "storage").mkdir(exist_ok=True)
    return path


def write_prefs(profile: Path, data_dir: Path | None, use_data_dir=True):
    profile.mkdir(parents=True, exist_ok=True)
    lines = ['// Mozilla User Preferences', 'user_pref("extensions.zotero.firstRun2", false);']
    if data_dir is not None:
        lines.append(f'user_pref("extensions.zotero.dataDir", {json.dumps(str(data_dir))});')
        lines.append(f'user_pref("extensions.zotero.useDataDir", {"true" if use_data_dir else "false"});')
    (profile / "prefs.js").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_prefs_types_and_escapes():
    text = "\n".join([
        "// comment line",
        'user_pref("extensions.zotero.dataDir", "/Users/g/Zotero Data");',
        'user_pref("extensions.zotero.useDataDir", true);',
        'user_pref("extensions.zotero.flag", false);',
        'user_pref("extensions.zotero.count", 42);',
        r'user_pref("x.win", "C:\\Users\\G\u00e1bor\\Zotero \"q\"");',
        "garbage that is not a pref",
    ])
    prefs = parse_prefs(text)
    assert prefs["extensions.zotero.dataDir"] == "/Users/g/Zotero Data"
    assert prefs["extensions.zotero.useDataDir"] is True
    assert prefs["extensions.zotero.flag"] is False
    assert prefs["extensions.zotero.count"] == 42
    assert prefs["x.win"] == 'C:\\Users\\Gábor\\Zotero "q"'


def test_profile_roots_per_os(tmp_path):
    home = tmp_path / "home"
    assert profile_roots("Darwin", home, {}) == [home / "Library" / "Application Support" / "Zotero"]
    assert profile_roots("Linux", home, {}) == [home / ".zotero" / "zotero"]
    appdata = tmp_path / "AppData" / "Roaming"
    assert profile_roots("Windows", home, {"APPDATA": str(appdata)}) == [appdata / "Zotero" / "Zotero"]
    assert profile_roots("Windows", home, {}) == []


def test_mac_profile_data_dir(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(tmp_path / "custom data")
    write_prefs(home / "Library/Application Support/Zotero/Profiles/abc.default", data_dir)
    result = resolve_data_dir("", system="Darwin", home=home, env={})
    assert result.path == str(data_dir)
    assert result.source.startswith("prefs:")


def test_default_home_zotero(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(home / "Zotero")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(data_dir)
    assert result.source == "default"


def test_use_data_dir_false_is_ignored(tmp_path):
    home = tmp_path / "home"
    default = make_data_dir(home / "Zotero")
    other = make_data_dir(tmp_path / "old place")
    write_prefs(home / ".zotero/zotero/p1.default", other, use_data_dir=False)
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(default)


def test_profiles_ini_default_profile_wins(tmp_path):
    home = tmp_path / "home"
    root = home / ".zotero" / "zotero"
    dir_a = make_data_dir(tmp_path / "A")
    dir_b = make_data_dir(tmp_path / "B")
    write_prefs(root / "a.default", dir_a)
    write_prefs(root / "b.default", dir_b)
    (root / "profiles.ini").write_text(
        "[General]\nStartWithLastProfile=1\n\n"
        "[Profile0]\nName=a\nIsRelative=1\nPath=a.default\n\n"
        "[Profile1]\nName=b\nIsRelative=1\nPath=b.default\nDefault=1\n", encoding="utf-8")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(dir_b)


def test_windows_appdata_profile(tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    data_dir = make_data_dir(tmp_path / "D")
    write_prefs(appdata / "Zotero/Zotero/Profiles/x.default", data_dir)
    result = resolve_data_dir("", system="Windows", home=home, env={"APPDATA": str(appdata)})
    assert result.path == str(data_dir)


def test_configured_path_wins(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero")
    configured = make_data_dir(tmp_path / "configured")
    result = resolve_data_dir(str(configured), system="Linux", home=home, env={})
    assert result.path == str(configured)
    assert result.source == "config"


def test_invalid_configured_path_does_not_fall_back(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero")
    result = resolve_data_dir(str(tmp_path / "nope"), system="Linux", home=home, env={})
    assert result.path is None
    assert result.source == "config"
    assert result.candidates[0].ok is False
    assert "zotero.sqlite" in result.candidates[0].reason


def test_tilde_expands_against_given_home(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(home / "Library" / "ZoteroData")
    result = resolve_data_dir("~/Library/ZoteroData", system="Darwin", home=home, env={})
    assert result.path == str(data_dir)


def test_nothing_found_lists_what_was_checked(tmp_path):
    result = resolve_data_dir("", system="Linux", home=tmp_path / "home", env={})
    assert result.path is None and result.source is None
    assert result.candidates
    assert all(c.ok is False and c.reason for c in result.candidates)


def test_missing_storage_is_ok_but_noted(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero", storage=False)
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(home / "Zotero")
    chosen = [c for c in result.candidates if c.ok][0]
    assert "storage" in chosen.reason


def test_unreadable_prefs_do_not_crash(tmp_path):
    home = tmp_path / "home"
    profile = home / ".zotero/zotero/bad.default"
    profile.mkdir(parents=True)
    (profile / "prefs.js").write_bytes(b"\xff\xfe\x00garbage\x00")
    make_data_dir(home / "Zotero")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(home / "Zotero")


def test_status_reports_data_dir(tmp_path):
    data_dir = make_data_dir(tmp_path / "Z")
    specs = {s.name: s for s in tools.tool_specs(lambda: Settings(zotero_data_dir=str(data_dir)))}
    out = json.loads(specs["zotero_status"].handler({}))
    assert out["ok"] is True
    assert out["data_dir"]["path"] == str(data_dir)
    assert out["data_dir"]["source"] == "config"
    assert isinstance(out["data_dir"]["checked"], list)
