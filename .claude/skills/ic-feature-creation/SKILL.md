---
name: ic-feature-creation
description: House rules for building a feature in the india_compliance app — server code shape, Desk form layout, and how tests are written. Use whenever the task adds or changes behaviour in this app: a new doctype or custom field, an override on an ERPNext doctype, a client script, a GST return section or payload mapping, an e-waybill/e-invoice change, or the tests for any of those. Reach for it before writing the first line, since the layout order, `@property` vs helper, patches.txt bump and whole-workflow test shape are all decided up front and expensive to retrofit.
---

# Building a feature in india_compliance

The app extends ERPNext, never forks it. Every rule below is checkable — the named file proves it.

`india_compliance/hooks.py` is the wiring index: overrides, client scripts, bundles, patches and
scheduled jobs all register there. Read it before hunting for where something is hooked up.

## Code

- **Transformation = mapping table + shared step** from `gst_returns/steps.py` (`take`, `pick`,
  `decode`). A new return section is data, not new code. See `gst_india/utils/gstr_2/sections/isd.py`
  — `KEYS_2A` dict, then `take`.
- **Never a raw string key.** Field names and code lists come from the constant classes in
  `gst_returns/fields/` and `gst_india/constants/`.
- `gst_returns/` stays frappe-free. `gst_returns/test_frappe_free.py` fails the build otherwise.
- **Extend, don't fork.** Change ERPNext or Frappe behaviour with a `doc_events` / `override_*` entry
  in `hooks.py` pointing at `gst_india/overrides/`. Never edit another app.
- **Derived value → `@property`** on the controller, not a loose helper. Many derived fields on one
  class → phantom fields instead of many properties (`EWaybillData`, `GSTTransactionData`).
- **One call site → inline it.** Don't add to `gst_india/utils/__init__.py` for a single caller.
- **Delete what you replaced**, in the same commit.
- **Client gate → same guard server-side.** A hidden button is not a permission check.
- **Custom field or property setter → bump the numbered patch** in `patches.txt`, or existing sites
  never receive it.

## UI

- **Field order = fill order.** Company, then posting date, then items, then taxes. The taxes table
  cannot sit above the items table.
- **Workflow unknown → ask before laying out the form.** Don't guess the order the user works in.
- **Match the sibling doctype.** Asset Movement looks and behaves like Stock Entry — copy its
  sections, actions and wording rather than inventing a second style.
- Client scripts: one file per doctype in `gst_india/client_scripts/`, `const DOCTYPE = "..."` at the
  top, thin handlers, logic in functions below.
- **`doctype_js` list order is load order.** A script calling `setup_e_waybill_actions` must be listed
  after the one that defines it, or the form dies with a `ReferenceError` and registers no handlers.
- Read `gst_settings`, `india_state_options`, `indian_registered_companies` from boot
  (`boot.py: set_bootinfo`) — no `frappe.call` for settings.
- Set link filters in `setup(frm)` via `frm.set_query`, not in `refresh`.
- Every user-facing string through `__()` / `_()`.

## Testing

- **New feature → one test walking the whole user workflow**, end to end, the way a user performs it.
  Not a scatter of unit tests.
- **Later bug → append a case** to that workflow test. Don't start a new file.
- **Test data in `setup` and `.json`** (`india_compliance/tests/test_records.json`). No inline dicts
  scattered through assertions.
- `frappe.tests.IntegrationTestCase`; `change_settings` for settings, `responses` for NIC/GSP,
  `time_machine` for date-gated logic. **Never hit a real API.**
- Run one module: `bench --site <test-site> run-tests --app india_compliance --module <dotted.path>`

## Worked examples

- Declarative mapping pipeline: [PR #4829](https://github.com/resilient-tech/india-compliance/pull/4829)
- Feature on an ERPNext doctype, UI copied from a sibling:
  [PR #4712](https://github.com/resilient-tech/india-compliance/pull/4712)
