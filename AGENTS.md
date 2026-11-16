# AGENTS.md

india_compliance — GST / Income Tax layer on ERPNext. Extends ERPNext, never
forks it.

## How to work

**Assumption-First Planning.**

- State assumptions before coding.
- Present both readings. Ask when the task is ambiguous.
- Say so when a simpler approach exists.

**Comments.**

- One line, saying why, where the code can't. `ic-house-style` has the rules, including the `# Law:` citation for code that carries out a law.

**Root Cause Fix, Minimal Diff.**

- Find every caller and fix the shared place once, not the reported path.
- Reuse existing functionality.
- Do not restyle, rename, or refactor adjacent code.
- Mention unrelated dead code; do not delete it.
- Trace every changed line to the request.

**Goal Driven Development.**

- Turn the task into a check before starting: "fix the bug" → "a test
  reproduces it, then passes"; "refactor X" → "tests pass before and after".
- Write multi-step plans as `step -> check` lines, then run the checks.

**Structured Reporting.**

- Keep reporting language as instructive.
- Report as `Changed path/file.py:42` — one line per changed file.
- Give no summary paragraph of the whole task unless asked.

## Setup and test

- Run app: `bench start`
- Lint: `pre-commit run --all-files`
- Test: `bench --site <test-site> run-tests --app india_compliance --module <dotted.path>`
- Use a throwaway `<test-site>`; the bootstrap writes and commits records.

## Stop and ask

- Missing repo context, or a file you were not pointed at needs changing.
- Anything destructive: `rm -rf`, force push, deleting data.

## Growing this setup

- Add a new rule as one line in the matching skill, with the reason.
- Create a skill when none fits and the rule will recur; add it to the table.
- Split a skill over ~150 lines by topic; delete a rule unused for six months.
- Put machine-specific recipes in agent memory, not here.