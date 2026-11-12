# The Markdown corpus (spec v1)

hermes-zotero works without any of this: by default it indexes the text Zotero itself extracted from your PDFs. This guide is for people who convert their papers to Markdown with a tool of their own choice and want the plugin to use that text instead. Better conversions give better search, structured tables and provenance flags, through the same four tools.

The plugin contains no converter, no OCR engine and no model, and it will never start one. The Markdown folder is the whole interface: a converter writes files into it, the plugin reads them. Point the plugin at the folder with the `markdown_path` setting.

## How the plugin picks a paper's text

For each Zotero item, in this order:

1. **A Markdown file** in the corpus folder that belongs to the item (matched by DOI, then by the item's key, then by the keys of its attachments).
2. **Zotero's full-text cache** (`.zotero-ft-cache` next to each stored attachment).
3. **Title and abstract** only.

Search hits and reads name the source (`markdown`, `ft-cache` or `metadata`).

## The spec

### Files

- One paper per file, UTF-8, directly in the folder or in its `library` subfolder.
- File name, either form:
  - `doi_<slug>.md`, where the slug is the DOI in lower case with every run of characters other than letters, digits, dots and hyphens replaced by one `_`. `10.1016/j.cmet.2019.05.003` becomes `doi_10.1016_j.cmet.2019.05.003.md`.
  - `K:<key>.md`, where the key is the eight-character Zotero key of the item or of one of its attachments, for papers without a DOI.
- Files smaller than 200 bytes are ignored.
- The plugin notices a changed file by its name, size and modification time, and re-indexes that paper on the next sync.

### Front matter (optional)

A file may start with a small header. Everything in it is optional, and a file without it is a valid v1 file.

```markdown
---
spec: 1
ocr: true
text_tool: docling 2.94
tables: structured
---
# Title of the paper
```

| Key | Value | Meaning |
| --- | --- | --- |
| `spec` | `1` | The version of this spec the file follows. |
| `ocr` | `true` or `false` | The body text came from OCR. The plugin puts the flag `ocr` on the paper. |
| `text_tool` | free text | The tool and version that produced the text. For your own records. |
| `tables` | `structured` | The file has a structured-tables section (below). For other tools; the plugin looks for the section itself. |

Rules:

- The opening `---` is the first line of the file, the next line is a `key: value` pair starting in the first column, and the closing `---` follows within 100 lines. A `---` anywhere else is an ordinary Markdown rule.
- Only top-level `key: value` lines are read. Indented lines, list items and comments are skipped; unknown keys are ignored. Values may be quoted.
- The header is not indexed and never appears in the text the tools return.

### Body

Plain Markdown. Headings (`#` to `######`) become the section names shown in search hits. A common layout is a title line, a few lines of metadata, the abstract, then the text of the paper. Text from further attachments of the same item can follow under a heading of its own.

### Structured tables (optional)

Tables can go into one section at the end of the file:

```markdown
## Tables (structured)

A note from the converter may stand here. It is not indexed.

### Table 1
Table 1. Baseline characteristics

<table>
<tr><th></th><th>Women</th><th>Men</th></tr>
<tr><td>Age (yr)</td><td>59 ± 11</td><td>58 ± 11</td></tr>
<tr><td>BMI (kg/m2)</td><td>27.1 ± 4.9</td><td>27.9 ± 4.1</td></tr>
</table>

### Table 2

| Marker | Level |
| --- | --- |
| Leptin | high |
```

- The marker line is exactly `## Tables (structured)`. Each table has a heading `### Table N`, optionally a caption on the lines after it, and then one table: HTML (`<table>`, `<tr>`, `<th>`, `<td>`) or a Markdown pipe table.
- Header rows are the leading rows made only of `<th>` cells (in a pipe table: the rows above the `| --- |` line).
- Keep the section last. Removing everything from the marker to the end of the file must give back the text without tables.

What the plugin does with it: every table is indexed and returned as pipe rows (`| a | b |`), with entities decoded and markup removed. A table is one search passage; a long one is cut at row ends, and every piece repeats the table's label and header rows. `zotero_search` with `in_tables` searches only these passages, and `zotero_read` with `mode` = `tables` lists a paper's tables or returns one.

Pipe tables in the body of a paper stay ordinary text. Converters often lay out multi-column prose and figures as pipe tables, so only the structured section is trusted.

### What does not belong in the corpus

Credentials, anything that writes back to Zotero, and anything that is not derived from your own attachments.

## Flags the plugin sets

| Flag | Set when | What it tells the agent |
| --- | --- | --- |
| `ocr` | the front matter says `ocr: true` | Digits and symbols may be wrong; say so when quoting numbers. |
| `text_damaged` | the text shows clear conversion damage: words run together, letters or ligatures missing, an unreadable font encoding | Rely on title and abstract; searches can miss the paper. |
| `truncated` | Zotero's text cache holds only the first pages | Results further on were not read. |
| `body_not_read`, `scanned_or_empty` | no text was found for the item | Only title and abstract are in the index. |

`text_damaged` is one-sided: set means damage was found; not set means no sign was found, not that the text is perfect. A paper with this flag is a good candidate for converting again with another tool.

## Producing a corpus

Any converter that writes the files above will do. A few rules keep it safe:

- **Never write to Zotero's data directory,** and do not open `zotero.sqlite` there while Zotero may be running. Work from a copy of the database. Stored attachments are at `storage/<attachment key>/` in the data directory.
- **Convert in an environment of its own,** not inside Hermes' Python environment: converters bring large dependencies and their own version constraints.
- **Keep what the converter produced** (its intermediate output) next to the corpus, so that a bad merge can be undone without converting again.
- **Long batch jobs:** a scheduled Hermes script that runs without the agent has a time limit of one hour. Split a large backlog into runs that stop on their own and continue next time.
- After new files are written, the next `hermes zotero sync` (or the agent's `zotero_sync`) picks them up.

## Tool recommendations

These are recommendations from the author's own use on a library of about 18,000 papers, not a benchmark. Use whatever serves your library.

- [Docling](https://github.com/docling-project/docling) (MIT licence) for text, OCR of scanned PDFs and tables. In the author's own trials on his papers it gave the best results of the tools he tried, at no cost. He set vendors' published comparisons aside, because each favoured its own product. Your papers may behave differently: try a sample of your own first.
- For batches, call Docling from Python rather than through its command line. In the author's runs the command line crashed on a small number of PDFs that the Python interface converted.
- Run OCR only where it is needed, for example when a PDF yields almost no text, and record it with `ocr: true`.
- Extract tables as cell strings and leave charts alone: turning chart images into numbers is unreliable.
- Hosted parsing services send your PDFs to someone else's servers. Check their cost, retention and licence terms before you use one for papers you may not redistribute.

## Versioning

`spec: 1` is this document. Later versions will only add optional keys and sections; a v1 file stays valid.
