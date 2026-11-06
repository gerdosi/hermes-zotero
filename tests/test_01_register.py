import argparse
import json


def test_register_tools_and_cli(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert "zotero_status" in fake_ctx.tools
    assert {t["toolset"] for t in fake_ctx.tools.values()} == {"zotero"}
    assert "zotero" in fake_ctx.cli


def test_handler_reads_config_at_call_time(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    handler = fake_ctx.tools["zotero_status"]["handler"]
    fake_ctx.config["sync_batch_items"] = 321
    assert json.loads(handler({}))["settings"]["sync_batch_items"] == 321


def test_cli_doctor(plugin_module, fake_ctx, capsys):
    plugin_module.register(fake_ctx)
    entry = fake_ctx.cli["zotero"]
    parser = argparse.ArgumentParser(prog="hermes zotero")
    entry["setup_fn"](parser)
    rc = entry["handler_fn"](parser.parse_args(["doctor"]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "hermes-zotero" in out
    assert plugin_module.__version__ in out


def test_cli_without_subcommand_prints_help(plugin_module, fake_ctx, capsys):
    plugin_module.register(fake_ctx)
    entry = fake_ctx.cli["zotero"]
    parser = argparse.ArgumentParser(prog="hermes zotero")
    entry["setup_fn"](parser)
    rc = entry["handler_fn"](parser.parse_args([]))
    assert rc == 0
    assert "doctor" in capsys.readouterr().out
