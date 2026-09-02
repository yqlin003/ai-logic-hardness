# Capability Specification — `gates.verify`

**Status:** current as of this branch. This documents what the gate runner
*does today*, not aspirations. See the README for philosophy and usage.

## 1. Overview

A dependency-free Python 3 CLI that inspects a pending change in a git
repository, runs eight verification gates, and renders a three-way verdict.

```bash
python3 -m gates.verify --config gates.config.json --root . --report gate-report.json
```

| Exit code | Decision  | Meaning |
|-----------|-----------|---------|
| `0`       | `approve` | Every gate passed with positive evidence. |
| `2`       | `abstain` | A gate failed **or** evidence was missing. Never approves on plausibility. |
| `3`       | error     | Configuration or execution error (bad JSON, unreadable files). |

Requires only Python (>= 3.11 for `pyproject.toml` parsing) and `git`.

## 2. What counts as "the change"

The union of three sources, so nothing can hide:

- **Unstaged edits** — `git diff <base>` (config key `base`, default `HEAD`).
- **Staged edits** — `git diff --cached`.
- **Untracked files** — `git ls-files --others --exclude-standard`; full
  contents are treated as additions, so new files cannot bypass scanners.

ANSI color codes are stripped before scanning.

## 3. The eight gates

| # | Gate | Passes when | Fails / blocks when |
|---|------|-------------|---------------------|
| 1 | `requirements` | Non-empty `requirements`, all non-blank | **Blocked** if empty or `ambiguities` remain; **fail** on blank entries |
| 2 | `invariants` | Non-empty `invariants`, all non-blank | **Blocked** if empty; **fail** on blank entries |
| 3 | `small_change` | <= `max_changed_files` (10) files and <= `max_changed_lines` (500) added+deleted lines; untracked files count full length | **Fail** over either limit |
| 4 | `tests` | `test_command` exits 0 (`test_timeout` 120s; last 4000 chars kept as evidence) | **Blocked** if unset; **fail** on non-zero exit or timeout |
| 5 | `independent_checks` | Every command exits 0 (`check_timeout` 120s each) | **Blocked** if none configured; **fail** if any fails |
| 6 | `security` | No secret pattern matches added lines (removals are ignored) | **Fail** on PEM private-key blocks, AWS access key IDs (`AKIA...`), or quoted `api_key`/`secret`/`token`/`password` assignments >= 8 chars |
| 7 | `dependencies` | All imports **and** manifest-declared packages approved (section 4) | **Fail** on unapproved packages; **blocked** on unverifiable files |
| 8 | `diff_audit` | `git diff --check` clean and every changed file matches an `allowed_paths` fnmatch pattern (recursive `**` supported) | **Fail** on either |

Any `fail` or `blocked` result makes the overall decision `abstain`; blocked
gates are additionally listed in `missing_evidence_gates`.

## 4. Dependency gate detail

**Import scanning** of added lines handles `import a`, `import a, b as c`,
and `from pkg.mod import x`; relative imports are skipped. Approved sources:
`allowed_dependencies`, the Python stdlib, local module stems, and local
package directories containing `__init__.py`.

**Manifest enforcement** — declared packages must appear in
`allowed_dependencies` even if never imported in the diff:

- `requirements*.txt` — line parser (comments and option lines skipped).
- `pyproject.toml` — `project.dependencies`, `optional-dependencies`,
  `dependency-groups`, `build-system.requires` (stdlib `tomllib`).
- `package.json` — `dependencies`, `devDependencies`, `peerDependencies`,
  `optionalDependencies`.
- Names compared with PEP 503 normalization (`Requests` == `requests`).
- **Unverifiable files** (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`,
  `Pipfile[.lock]`, `poetry.lock`, `uv.lock`, `setup.py`, `setup.cfg`) block
  until listed in `reviewed_dependency_files` after human review.
- Deleted manifests introduce no dependencies; malformed or unreadable
  manifests block rather than pass silently.

## 5. Configuration keys

`base`, `requirements`, `ambiguities`, `invariants`, `max_changed_files`,
`max_changed_lines`, `test_command`, `test_timeout`, `independent_checks`,
`check_timeout`, `allowed_dependencies`, `reviewed_dependency_files`,
`allowed_paths`. See `examples/gates.config.json` for a working template.

## 6. Report format

`gate-report.json` records `decision`, `abstain`, `failed_gates`,
`missing_evidence_gates`, and per-gate `{name, status, summary, evidence}` —
changed files, line counts, command outputs, pattern names, and offending
package names. Suitable for audit logs or structured feedback to an agent.

## 7. Continuous integration

`.github/workflows/ci.yml` runs the test suite on every pull request, then
runs the gate runner against the PR's merge-base diff and uploads the report
as a build artifact. A failing check means the verifier abstained.

## 8. Explicit non-capabilities

- Does **not** prove logical correctness; it only shows no configured red
  flag exists.
- Secret patterns cover three families; vendor token formats (GitHub,
  OpenAI, Slack) and unquoted `ENV=value` assignments are not yet detected.
- Commands run via `shlex` without a shell — no pipes or `&&`.
- No rename detection; a rename counts as add plus delete.
- The policy file itself is editable in a change, so policy edits need
  human review.
- Dynamic imports (`importlib.import_module("x")`) are not caught.
