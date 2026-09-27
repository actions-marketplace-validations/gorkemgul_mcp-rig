# MCP Rig CI and Package Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only GitHub Actions gates that test MCP Rig on Python 3.11–3.13, dogfood both CLI commands, and validate installable wheel and source distributions.

**Architecture:** Make the checked-in fixture suite environment-portable first, then add one workflow with a three-version `test` matrix and a dependent single-version `package` job. Validate configuration structurally and execute the same commands locally; the pull request's hosted GitHub Actions run is the final environment-level gate.

**Tech Stack:** GitHub Actions, Python 3.11–3.13, Hatchling/build, Twine, pytest, Ruff, PyYAML, MCP Rig CLI

**Spec:** `docs/superpowers/specs/2026-09-27-ci-package-validation-design.md`

## Global Constraints

- Run on ordinary `pull_request` events and pushes to `main`; never use `pull_request_target`.
- Set workflow-level permissions to `contents: read`; reference no secrets, environments, or OIDC permissions.
- Use `actions/checkout@v7` and `actions/setup-python@v7`; introduce no third-party actions.
- Test Python `3.11`, `3.12`, and `3.13` on `ubuntu-latest` with `fail-fast: false`.
- Do not publish artifacts, upload to PyPI/TestPyPI, create tags/releases, or change the project version.
- Preserve all Python source behavior and runtime dependency declarations.
- The approved configuration exception replaces per-line TDD with structural parsing, real local commands, and the pull request's hosted workflow result.

## Review Focus

- `examples/fixture.yaml` must use the selected/activated Python from `PATH`, while its fixture script remains suite-relative; prove this through the real public CLI in Task 1.
- YAML tooling must preserve the trigger key as `on`, not coerce or rewrite it as a boolean; inspect the parsed structure and raw key in Task 2.
- The package job must depend on the complete matrix and never run as an independent publish path; assert `needs: test` in Task 2.
- Wheel smoke must run both `mcp-rig` and the fixture server with the fresh wheel environment, never the source checkout's interpreter; execute that exact boundary in Task 2.
- No write permission, secret, environment, publish command, or artifact upload may enter the workflow; inspect the complete workflow text in Task 2.

---

### Task 1: Portable Dogfood Example and Documentation

**Files:**
- Modify: `examples/fixture.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing suite-relative `cwd` behavior from `load_suite()` and the installed `mcp-rig run`/`check` commands.
- Produces: an example suite that launches `python` from `PATH`, plus local setup instructions that activate `.venv` before public CLI examples.

- [ ] **Step 1: Record the current non-portable example failure boundary**

From the repository root, run:

```text
PATH=/usr/bin:/bin .venv/bin/mcp-rig run examples/fixture.yaml
```

The deliberately restricted `PATH` contains no project Python environment.
The current example nevertheless reaches the fixture through its hard-coded
`../.venv/bin/python` command.

Expected: the suite reports three passing cases even though the selected
`PATH` cannot supply its interpreter. Record this successful-but-wrong behavior
as configuration RED evidence in the ledger; portability requires the example
to honor `PATH`.

- [ ] **Step 2: Make the example interpreter environment-portable**

Change only the example command and its usage comment:

```yaml
# From the repository root with the development environment activated:
# mcp-rig run examples/fixture.yaml --junit /tmp/mcp-rig-results.xml
server: python ../tests/fixtures/fixture_server.py
```

Keep all three cases and expectations unchanged.

- [ ] **Step 3: Update local usage documentation**

In `README.md`:

- add `source .venv/bin/activate` to development setup;
- use `mcp-rig` rather than `.venv/bin/mcp-rig` in suite/check examples;
- state that repository CI tests Python 3.11–3.13 and validates wheel/sdist output without publishing; and
- keep the existing safety warning for `--probe-invalid-args` unchanged.

- [ ] **Step 4: Prove the portable example through the public CLI**

With `.venv/bin` first on `PATH`, run:

```bash
mcp-rig run examples/fixture.yaml --junit /tmp/mcp-rig-ci-plan.xml
mcp-rig check "python tests/fixtures/fixture_server.py"
```

Expected: suite summary `3 passed, 0 failed, 0 errors, 0 skipped`, valid JUnit XML, and `3/3 checks passed`; both commands exit 0.

- [ ] **Step 5: Run regression verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/python -m pip check && git diff --check`

Expected: all tests and lint pass, dependencies are consistent, and the working-tree diff has no whitespace errors.

- [ ] **Step 6: Commit the portable example**

```bash
git add examples/fixture.yaml README.md
git commit -m "docs: make the fixture example environment portable"
```

---

### Task 2: Read-Only Test Matrix and Distribution Gate

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the portable example from Task 1, `pyproject.toml` build metadata, the complete test suite, and both public CLI commands.
- Produces: a `ci` workflow with `test` matrix and dependent `package` jobs whose exit status gates pull requests and `main` pushes.

- [ ] **Step 1: Create the workflow with exact triggers and security boundary**

Define:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

Do not add any other permission, secret, environment, scheduled trigger, manual trigger, or publish event.

- [ ] **Step 2: Add the complete Python test matrix**

Create `test` on `ubuntu-latest` with `fail-fast: false` and exact string values `"3.11"`, `"3.12"`, and `"3.13"`. Use checkout/setup-python v7, pip cache keyed by `pyproject.toml`, and named steps for:

```text
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check src tests
pytest -q
python -m pip check
mcp-rig run examples/fixture.yaml --junit report.xml
mcp-rig check "python tests/fixtures/fixture_server.py"
```

- [ ] **Step 3: Add the dependent distribution job**

Create `package` with `needs: test`, `ubuntu-latest`, and Python `3.13`. Use checkout/setup-python v7 and named steps that:

```text
python -m pip install --upgrade pip
python -m pip install build twine
python -m build
python -m twine check dist/*
```

The final Bash step creates `$RUNNER_TEMP/mcp-rig-wheel`, installs `dist/*.whl`, and invokes:

```text
$RUNNER_TEMP/mcp-rig-wheel/bin/mcp-rig check "$RUNNER_TEMP/mcp-rig-wheel/bin/python tests/fixtures/fixture_server.py"
```

No artifact-upload or publish step follows it.

- [ ] **Step 4: Parse and inspect the workflow structure locally**

Use `.venv/bin/python` and `yaml.BaseLoader` so YAML 1.1 boolean coercion cannot hide the raw `on` key. Assert:

- top-level keys include literal `on`, `permissions`, `concurrency`, and `jobs`;
- triggers are exactly `push` to `main` and `pull_request`;
- permissions equal only `{contents: read}`;
- test matrix versions equal `3.11`, `3.12`, `3.13` and fail-fast is false;
- `package.needs` is `test`;
- every action reference is checkout v7 or setup-python v7; and
- raw workflow text contains none of `pull_request_target`, `secrets.`, `id-token`, `environment:`, `upload-artifact`, `twine upload`, or `pypa/gh-action-pypi-publish`.

Expected: every assertion passes.

- [ ] **Step 5: Execute the local equivalents of the matrix gate**

Run: `.venv/bin/ruff check src tests && .venv/bin/python -m pytest -q && .venv/bin/python -m pip check`

Then put `.venv/bin` first on `PATH` and run both Task 1 dogfood commands again.

Expected: all checks and both public CLI commands exit 0.

- [ ] **Step 6: Build and validate both distributions**

Install `build` and `twine` into the development environment if absent, then run:

```text
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Expected: exactly one `mcp_rig-0.1.0-py3-none-any.whl` and one `mcp_rig-0.1.0.tar.gz`; every Twine check passes.

- [ ] **Step 7: Prove the wheel in a fresh environment**

Create a new temporary directory with `mktemp -d`, create a virtual environment inside it, install only `dist/mcp_rig-0.1.0-py3-none-any.whl`, and run the wheel-installed command with the wheel environment's Python as the fixture interpreter.

Expected: `3/3 checks passed`, nine fixture lint warnings, and exit 0.

- [ ] **Step 8: Run final local verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/python -m pip check && git diff --check`

Expected: all tests and lint pass, dependencies are consistent, and the working-tree diff has no whitespace errors.

- [ ] **Step 9: Commit the workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: test supported Python versions and packages"
```

---

### Hosted Acceptance Gate

After native execution, whole-branch review, and PR creation:

1. wait for every Python 3.11/3.12/3.13 matrix check and the dependent package job;
2. if any check fails, inspect `gh run view --log-failed`, reproduce when possible, and fix it test/config-first on this branch;
3. push fixes and wait for the newest non-cancelled run; and
4. merge only when GitHub reports the complete workflow successful.

The hosted run is required evidence, not an optional post-merge observation.
