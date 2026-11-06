"""Hermes glue for hermes-zotero. All logic lives in zotcore/."""
# pytest >= 8 imports this file "bare" (without a parent package) while collecting tests,
# where relative imports fail. Hermes always loads it as a package, so everything sits
# under this guard.
if __package__:
    from pathlib import Path

    from .zotcore import __version__, cli, tools
    from .zotcore.citation import ZOTERO_LOCAL_API
    from .zotcore.settings import Settings
    from .zotcore.skill import SKILL_DESCRIPTION, SKILL_NAME, skill_path

    def register(ctx):
        def settings() -> Settings:
            return Settings.from_getter(ctx.get_config)

        def data_root():
            from plugins.plugin_storage import plugin_data_dir  # Hermes public API; per-profile folder
            return plugin_data_dir("hermes-zotero")

        for spec in tools.tool_specs(settings, data_root=data_root, citation_api=ZOTERO_LOCAL_API):
            ctx.register_tool(name=spec.name, toolset="zotero", schema=spec.schema,
                              handler=spec.handler, description=spec.description, emoji="📚")

        register_skill = getattr(ctx, "register_skill", None)
        skill_md = skill_path(Path(__file__).resolve().parent)
        if register_skill is not None and skill_md.is_file():
            register_skill(SKILL_NAME, skill_md, description=SKILL_DESCRIPTION)

        ctx.register_cli_command(
            name="zotero",
            help="Local, read-only Zotero library index",
            setup_fn=cli.setup_parser,
            handler_fn=lambda args: cli.run(args, settings(), data_root=data_root),
            description="Check and maintain the local Zotero index used by the zotero_* tools.",
        )
