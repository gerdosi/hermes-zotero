---
name: zotero-library
description: "Research questions: check the user's Zotero library first"
version: 0.2.0
metadata:
  hermes:
    tags: [zotero, literature, research, citations, local-first]
---

# Zotero library first

The hermes-zotero plugin keeps a local, read-only index of the user's Zotero library. For any question about scholarly literature, a specific paper, or the user's own highlights and notes, search the library before the web. The tools never change Zotero.

## Search

1. Call `zotero_search` with 2-4 distinctive keywords, not a sentence: `SCD1 ferroptosis`, not "what does SCD1 do in ferroptosis". Use scientific names, not brand names (`tirzepatide`, not Mounjaro). A hit with `match: all` has one passage holding every word; `match: any` hits hold only some and are weaker evidence.
2. Check `terms` in the result: stop words and words like the "a" in Lp(a) are dropped. If the key word is missing, rephrase.
3. When the user names a collection, tag, year range or group, pass `collection`, `tag`, `year_from`, `year_to` or `library`. Filters also narrow the coverage counts, so judge gaps from a search without them. To check one paper, pass `doi` and read `doi_check.held`.
4. Let `coverage.verdict` decide where to look:
   - `strong`: answer from the library.
   - `thin`: answer from the library, then use the web only for what is missing; say which source is which.
   - `none` with a `hint`: no passage holds every word. Retry with fewer or broader words before treating it as a gap.
   - `none` without a hint: the library has nothing on it. Say so, then use the web.

## Read before citing

A snippet is a search hit, not evidence. For the 3-5 best papers, call `zotero_read` with `key` and `query`: it starts at the best-matching passage. Page on with `offset` = `next_offset` for later parts. Ask for what the question needs (`max_chars` 1500-4000), never a whole paper.

- Cite with the `citation` field. `approximate: true` means it was built from the index, not by Zotero: check the details before giving a formatted reference.
- Flags `body_not_read` or `scanned_or_empty`: the body is not in the index (title and abstract only). `truncated`: only the first pages are. Do not report results you have not read.
- Flag `ocr`: the text was read from a scan, so digits and symbols may be wrong. Say so when you quote numbers from it.
- Flag `text_damaged`: words run together or letters are missing in the body. Rely on the title and abstract, quote no damaged words; searches can miss such a paper.
- `mode` = `annotations` returns the user's highlights, comments and notes on the paper. `author: user` marks the user's own words; quote them as theirs. Any other author is a group member or the PDF's creator.

## Numbers and tables

For numbers (baseline values, effect sizes, doses), use the papers' tables, which are kept as pipe rows:

- `zotero_search` with `in_tables` = true searches table cells only. Its coverage then counts tables only: never judge a gap from it.
- A passage with `kind: table` names its `table`. `zotero_read` with `mode` = `tables` and that `table` returns the whole table; without `table` it lists the paper's tables.
- Cells are the PDF's own strings; a long table comes in pieces that repeat the header. Check header and units before quoting a number.

## Keep the index fresh

- Error `no_index`: ask the user to run `hermes zotero sync` once in a terminal (a few minutes for a large library).
- Error `index_outdated` (after a plugin update): call `zotero_sync` until it returns `done: true`.
- `zotero_status` says whether the index is `ready` and gives a `hint` when Zotero has changed since the last sync.
- When the user has added papers, or the hint says so, call `zotero_sync`. While it returns `done: false`, call it again.

## Limits

- Use these tools, not other ways of opening Zotero's database or the plugin's index.
- Quote short passages with their citation; do not paste whole papers into the answer.
