# AGENTS.md

india_compliance — GST / Income Tax layer on ERPNext. Extends ERPNext, never
forks it.

## Setup and test

- Run app: `bench start`
- Lint: `pre-commit run --all-files`
- Test: `bench --site <test-site> run-tests --app india_compliance --module <dotted.path>`
- Use a throwaway `<test-site>`; the bootstrap writes and commits records.

## Comments

- One line, saying why, where the code can't. `ic-house-style` has the rules, including the `# Law:` citation for code that carries out a law.

## Stop and ask

- Missing repo context, or a file you were not pointed at needs changing.
- Anything destructive: `rm -rf`, force push, deleting data.

## Growing this setup

- Add a new rule as one line in the matching skill, with the reason.
- Create a skill when none fits and the rule will recur; add it to the table.
- Split a skill over ~150 lines by topic; delete a rule unused for six months.
- Put machine-specific recipes in agent memory, not here.
