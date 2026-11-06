import json

from zotcore import __version__, tools
from zotcore.settings import Settings


def specs(provider=Settings):
    return {spec.name: spec for spec in tools.tool_specs(provider)}


def test_status_tool_exists_and_schema_is_well_formed():
    all_specs = specs()
    assert "zotero_status" in all_specs
    for name, spec in all_specs.items():
        assert spec.schema["name"] == name
        assert isinstance(spec.schema["description"], str) and 20 <= len(spec.schema["description"]) <= 1024
        # Tool Search lists the first ~60 characters: they must say what library this is.
        assert "Zotero" in spec.schema["description"][:60]
        assert spec.schema["parameters"]["type"] == "object"
        assert name.startswith("zotero_")


def test_status_returns_json_string():
    out = specs()["zotero_status"].handler({})
    assert isinstance(out, str)
    data = json.loads(out)
    assert data["ok"] is True
    assert data["plugin_version"] == __version__
    assert data["settings"]["libraries"] == ["user"]
    assert data["warnings"] == []


def test_handler_tolerates_junk_args_and_kwargs():
    handler = specs()["zotero_status"].handler
    assert json.loads(handler({"junk": 1}, task_id="t1"))["ok"] is True
    assert json.loads(handler(None))["ok"] is True


def test_handler_never_raises():
    def broken_provider():
        raise RuntimeError("kaboom")
    handler = specs(broken_provider)["zotero_status"].handler
    data = json.loads(handler({}))
    assert data["ok"] is False
    assert data["error"]["code"] == "internal_error"
    assert "kaboom" in data["error"]["message"]
