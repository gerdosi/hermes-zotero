# Task 06b — One unreadable file must not block the sync

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low** is enough: the change is fully specified (this repo now defaults to high, which is fine too) |
| Budget | ≤ 20 tool calls |
| Depends on | task 06 committed |
| Done when | `.venv/bin/python -m pytest` shows **87 passed**, checksum matches, report committed |

## Why

Task 06's report asked what should happen when a text file disappears or can't be read between the stat and the read. Review confirmed a real problem. `choose_text` raises `OSError`, the whole batch of up to 200 items rolls back, and if the problem persists (a permission error, or a cloud-only file that won't download), **every later sync stops at the same batch**. The items after it are then never indexed. The new test reproduces this; on the task 06 code both its tests fail.

## Files

```
modify  zotcore/index.py
create  tests/test_06b_read_errors.py   (verbatim, below)
create  tasks/06b-report.md
commit  .claude/settings.json, AGENTS.md, tasks/README.md, tasks/04-read-items.md, tasks/05-text-and-passages.md,
        tasks/06-index-and-sync.md, tasks/06b-read-errors.md   (added or updated by Gábor; commit them as they are)
```

## Spec

1. In `zotcore/index.py`, import `TextResult` from `.textsource` as well, and add a module constant `MAX_ITEM_WARNINGS = 20`. Keep calling `choose_text` through the module-level name; the test replaces `zotcore.index.choose_text`.
2. In `sync`, keep a counter `read_errors = 0`. Wrap **only** the `choose_text(...)` call in `try/except OSError as e`. On error:
   - `read_errors += 1`. While `read_errors <= MAX_ITEM_WARNINGS`, append the warning `item <key>: could not read text (<e>); indexed title and abstract only`.
   - Use `TextResult("metadata", <title and abstract joined by a blank line, empty parts skipped>, None, ("body_not_read", "read_error"), signature)`, where `signature` is the `text_signature` already computed for this item. Because the signature is unchanged, an unchanged file is **not** retried on every run; a changed file is.
   - Continue with `split_passages` and `upsert` as usual, and count it in `indexed`.
3. Before setting `last_sync`, add one summary warning when `read_errors > 1`: `<n> items could not be read`, or, when `read_errors > MAX_ITEM_WARNINGS`, `<n> items could not be read; only the first 20 are listed`.
4. Nothing else changes. Other exceptions still propagate.

## Acceptance test (copy verbatim, then verify checksum)

| File | SHA-256 |
| --- | --- |
| `tests/test_06b_read_errors.py` | `136ca8f3f184ba47828d361a8af55b890ce59448acc1f1ea589ecca052f31655` |

### `tests/test_06b_read_errors.py`

```python
import pytest

import zotcore.index as index_module
from tests.zfixture import ZoteroFixture
from zotcore.index import Index, sync


@pytest.fixture
def lib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    for n in range(5):
        iid = z.add_item(f"PAPER00{n}", fields={"title": f"Paper {n}", "abstractNote": f"Abstract {n}."})
        z.add_attachment(iid, f"PDF0000{n}", ft_text=f"Body text number{n} about adipose tissue.\n\n" * 20)
    index = Index(tmp_path / "idx.sqlite")
    yield z, index
    index.close()
    z.close()


def test_unreadable_text_does_not_block_the_sync(lib, monkeypatch):
    z, index = lib
    real = index_module.choose_text

    def flaky(item, data_dir, corpus=None):
        if item.key == "PAPER002":
            raise PermissionError(13, "Permission denied", "/Zotero/storage/PDF00002/.zotero-ft-cache")
        return real(item, data_dir, corpus)

    monkeypatch.setattr(index_module, "choose_text", flaky)
    rep = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep.done is True and rep.indexed == 5  # the other four are indexed, and so is PAPER002 (metadata only)
    assert any("PAPER002" in w and "Permission denied" in w for w in rep.warnings)
    row = index.con.execute("SELECT text_source, flags FROM items WHERE item_key='PAPER002'").fetchone()
    assert row[0] == "metadata"
    assert "read_error" in row[1] and "body_not_read" in row[1]
    found = index.con.execute("SELECT item_key FROM passages WHERE passages MATCH 'abstract'").fetchall()
    assert ("PAPER002",) in found  # title and abstract are still searchable
    assert index.counts()["flags"]["read_error"] == 1

    # Unchanged files are not retried on every run ...
    rep2 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep2.indexed == 0 and rep2.warnings == ()

    # ... but once the file changes and becomes readable, the item is re-indexed with its full text.
    monkeypatch.setattr(index_module, "choose_text", real)
    z.write_ft_cache("PDF00002", "Fixed body text about mitochondrial uncoupling.\n\n" * 20)
    rep3 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep3.indexed == 1
    assert index.con.execute("SELECT text_source FROM items WHERE item_key='PAPER002'").fetchone()[0] == "ft-cache"


def test_many_read_errors_are_summarised(lib, monkeypatch):
    z, index = lib

    def broken(item, data_dir, corpus=None):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(index_module, "choose_text", broken)
    rep = sync(index, z.db_path, z.data_dir)
    assert rep.done is True and rep.indexed == 5
    assert len(rep.warnings) <= 21  # at most 20 item warnings plus one summary line
    assert any("5 items" in w and "could not be read" in w for w in rep.warnings)
```

## Commands

```bash
.venv/bin/python -m pytest                       # expect: 87 passed
shasum -a 256 tests/test_06b_read_errors.py
```

Finish with `tasks/06b-report.md` and one commit: `task 06b: unreadable files no longer block sync`.
