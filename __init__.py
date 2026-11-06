"""Hermes glue for hermes-zotero. All logic lives in zotcore/."""
from .zotcore import __version__, cli, tools
from .zotcore.settings import Settings


def register(ctx):
    def settings() -> Settings:
        return Settings.from_getter(ctx.get_config)

    for spec in tools.tool_specs(settings):
        ctx.register_tool(name=spec.name, toolset="zotero", schema=spec.schema,
                          handler=spec.handler, description=spec.description, emoji="📚")

    ctx.register_cli_command(
        name="zotero",
        help="Local, read-only Zotero library index",
        setup_fn=cli.setup_parser,
        handler_fn=lambda args: cli.run(args, settings()),
        description="Check and maintain the local Zotero index used by the zotero_* tools.",
    )
