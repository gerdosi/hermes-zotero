# Task 01b — Make the tests run on current pytest

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code (or DeepSeek V4.1 Flash 1017 in Hermes) |
| Reasoning | **low** |
| Budget | ≤ 15 tool calls |
| Depends on | task 01 committed |
| Done when | `.venv/bin/python -m pytest` shows **23 passed** on the **current** pytest, checksums unchanged, commit made |

## Why

Task 01's report found that pytest 8 and newer import the repo root `__init__.py` "bare", without a parent package, while collecting tests, so its relative imports fail. That was a flaw in the task's design, not in your work, and pinning `pytest<8` was the right call under the rules. The fix is a guard in `__init__.py`. It is tested on pytest 7.4, 8.4, 9.1 and 9.2, and Hermes' loader and validator still find `register()`.

## Files

```
modify  __init__.py            (replace with the content below, verbatim)
modify  tasks/01-report.md     (update the Deviations entry)
commit  AGENTS.md, tasks/README.md, tasks/01b-pytest-fix.md, tasks/03-snapshot.md   (already updated by Gábor; commit them as they are)
```

Do not touch `tests/`, `zotcore/` or `pyproject.toml`.

## Steps

1. Replace `__init__.py` with exactly:

```python
"""Hermes glue for hermes-zotero. All logic lives in zotcore/."""
# pytest >= 8 imports this file "bare" (without a parent package) while collecting tests,
# where relative imports fail. Hermes always loads it as a package, so everything sits
# under this guard.
if __package__:
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
```

2. Upgrade the development environment to the current pytest: `.venv/bin/python -m pip install -U pytest`.
3. Run `.venv/bin/python -m pytest`. Expect **23 passed**. Note the pytest version (`.venv/bin/python -m pytest --version`).
4. Run `shasum -a 256 tests/conftest.py tests/test_01_*.py`. The hashes must be unchanged from the task 01 report.
5. In `tasks/01-report.md`, replace the `pytest<8` deviation with: `Resolved in task 01b: root __init__.py now guarded with "if __package__:"; 23 passed on pytest <version>.`
6. Commit everything listed under Files with the message `task 01b: run tests on current pytest`.

If step 3 fails, stop and report the full error output. Do not pin pytest again.
