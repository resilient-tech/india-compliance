
---
name: ic-house-style
description: How code reads in india_compliance — plain words, one-line comments, when a function may exist, file and class order, and the structure rules for code that mirrors a government template or API. Load before writing or changing any code, comment, or name in this app.
---
# House style

Short, because long rules rot.

## Words

Plain English a non-programmer would guess. Same word for the same thing
everywhere.

| Say                         | Not       |
| --------------------------- | --------- |
| raw data, the portal's data | payload   |
| our row, the sync's row     | canonical |
| as it is                    | verbatim  |
| formatter                   | presenter |
| special case                | quirk     |
| totals                      | headline  |
| top-left cell               | anchor    |

Domain shorthand is fine: gstin, itc, b2b, cdnr, row, col.
No other abbreviations. record, not rec.
Booleans read as a question: is_amended, has_missing_sync.
A string compared in an if gets a name. A string that is a map key stays
  a key.

      if base == TCS_PERIOD:                 # named: it is logic
      "tax period of gstr 8": gstr8_period,  # not named: it is data

## Comments

One line. Only where the code can't say it.

Say why, not what. Never restate the name or the signature.
Delete it if the line below already reads clearly.
Function over about 12 lines? Mark its steps in one to three words, in order:

# validate, # queue; # headers, # rows, # write.

Deliberate shortcut? # ponytail: <the ceiling></the>, <the upgrade path></the>.

Good

    # SEZ carry the supplier under sgstin/tdname
    # portal has no amended-TDS category

Bad

    # This function iterates the SHEETS registry and, for each sheet, looks up
    # the block, applies the amended filter where one is set, and renders rows.

## Docstrings

One line, or none.

Module: what lives here.
Function: only when the name cannot carry it.
Test: what breaks if it fails.
No bullet lists, no command snippets, no design notes. Those go in docs.

## Functions

A function exists when two places call it, or when its body is a job of its own
that the caller should not have to read. Otherwise inline it.

    # before: one caller, four lines
    def remap_2a_sections(raw): ...
    def raw_sections(raw): return remap_2a_sections(raw)

    # after
    def raw_sections(raw):
        raw = raw or {}
        renamed = {ours: raw[gov] for ours, gov in GOV_KEYS_2A.items() if raw.get(gov)}
        return {**raw, **renamed}

Called only inside its own class? Underscore it: _section_groups.
Called from another class, module, or test? Plain name: rows_for.
Hooks a subclass fills in stay plain: fill, fill_readme.
Derived value on a controller: @property, not a loose helper. Many derived
  values on one class: phantom fields (EWaybillData, GSTTransactionData).

## Order

A file reads top to bottom in the order the work happens. A class does too.

    class GSTR2AExporter:
        FIELDS = ...          # data first
        SHEETS = ...

        def fill(self):       # entry point
        def _raw_gstins(...)  # helpers, in the order fill calls them
        def _section_groups(...)
        def _build_rows(...)
        def fill_readme(self) # what build calls after fill

Group module-level helpers under a one-line section comment when a file has
several kinds: # ---- formatters, # ---- periods and file names.

## Structure

**Mirror the source.** Code that implements an outside document, a government
Excel template or an API spec, is ordered the way that document is ordered and
keyed by the names it uses. The reader keeps both open side by side.

    SHEETS = {
        # sheet: (reader category, record list key, item list key)
        "B2B": ("B2B", raw2a.INVOICES, raw2a.ITEMS),
        "ISDA": NOT_FILLED,  # portal's 2A has no ISDA category
    }

**List every case, name the gaps.** A missing entry is invisible. NOT_FILLED
with a one-line reason is a decision someone made.

**Outside keys live in one file.** Never a bare "docdata" in logic.
gst_returns/fields/ is that file, and gst_returns/ stays frappe-free;
gst_returns/test_frappe_free.py guards it.

**Transformation = mapping table + shared step.** A new return section is data,
not new code: a KEYS dict, then take/pick/decode from
gst_returns/steps.py. See gst_india/utils/gstr_2/sections/isd.py.

**Resolve by name, not position.** cell(4, 3) breaks silently when the source
shifts a row. Match on the header label.

**Shared map, small override.** Measure the overlap before splitting one map per
case; duplicated mappings drift apart. Special cases go in one override keyed by
the sheet and the header as it reads.

    SHEET_FIELDS = {
        "B2B-DNRA": {"revised details | tax amount": doc.CESS},  # mis-merged headers
    }

**One value language.** Every map entry is a key, a (key, formatter) pair, or
a computed(source, exporter) function. Computed columns are map entries, not
if chains.

    "place of supply": (raw2a.POS, state_from_code),
    "trade/legal name": supplier_name,

**One resolver.** The runtime path and any report share it. A report that
reimplements the lookup will disagree with the code it reports on.

**Files can be large. Functions must be honest.** One job each, and the name
says the job. Split a file when it holds unrelated jobs, not when it gets long.
