# CLAUDE.md

india_compliance — GST / Income Tax layer on ERPNext. Extends ERPNext, never forks it.

- Output only what is asked.
- If uncertain: say UNKNOWN or omit. Do not guess.
- Bullets > prose. Prefer deletion over verbosity.
- Do not rewrite whole files; make surgical edits.
- **Write ZERO comments** — no one-liners, banners, TODOs, or docstrings. Leave the exsisting comments alone. The only exception: a docstring on a `@frappe.whitelist()` method, and only when I ask for it.
- Cite as `path/file.py:42`. No summary `.md` files.

## Setup / Test
- Run app: `bench start`
- Lint: `pre-commit run --all-files`
- Test: `bench --site <test-site> run-tests --app india_compliance --module <dotted.path>`

## Skills
- Adding or changing behaviour, form layout, or tests → `ic-feature-creation`

## Stop Conditions
- Missing repo context → ask / stop
- Files I didn't name → say so, ask first
- Destructive ops (rm, force push, prod site, `bench migrate` on a live site) → stop
- Rule needs more than a line → make it a skill, not a paragraph here
