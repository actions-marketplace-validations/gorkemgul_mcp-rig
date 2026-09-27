# MCP Rig PyPI Release Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete PyPI metadata and a manually approved, tokenless GitHub Release workflow that publishes verified MCP Rig distributions through PyPI Trusted Publishing.

**Architecture:** Enrich and test the package metadata first, then add one standard-library release-tag validator shared by local tests and the workflow. A dedicated release workflow builds and tests with read-only access, transfers exactly one wheel and one sdist through a short-lived artifact, and gives only a separate protected publish job OIDC permission.

**Tech Stack:** Python 3.13, Hatchling, pytest, Ruff, build, Twine, GitHub Actions, PyPI Trusted Publishing/OIDC

**Spec:** `docs/superpowers/specs/2026-09-27-pypi-release-publishing-design.md`

## Global Constraints

- Keep distribution name `mcp-rig`, version `0.1.0`, Python `>=3.11`, existing dependencies, CLI entry point, Hatchling backend, and runtime behavior unchanged.
- Trigger publishing only from a stable GitHub Release `published` event; expose no tag-push, branch, pull-request, schedule, or `workflow_dispatch` publication path.
- Use a separate read-only build job and a dependent `publish` job whose only permission is `id-token: write`.
- Publish through the GitHub environment `pypi`; use no PyPI password, API token, repository secret, TestPyPI, or local Twine upload.
- Pin every external action to a full immutable commit SHA and retain the reviewed release version in an adjacent YAML comment.
- Do not enable `skip-existing`, disable attestations, attach GitHub Release assets, change the project version, or create a GitHub Release during implementation.
- Treat creation of the real `v0.1.0` GitHub Release as a later irreversible action requiring separate explicit user confirmation.

## Review Focus

- A release tag such as `0.1.0`, `v0.1.1`, an empty tag, or a version with surrounding text must fail before distributions are built; Task 2 tests every case against the shared validator.
- A prerelease event must make both jobs ineligible even though the workflow event is `release: published`; Task 3 structurally asserts both job conditions.
- The OIDC-enabled publish job must never check out or execute repository code; Task 3 asserts that it has no `run` step and only download/publish actions.
- Stale or extra files in `dist/` must not enter publication; Task 3 requires a clean build and an exact two-file filename assertion before artifact upload.
- Package metadata must survive both wheel and sdist generation, including the license file and project URLs; Task 1 inspects both built distributions rather than only `pyproject.toml`.

---

### Task 1: PyPI Metadata and Installation Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `tests/test_package_metadata.py`

**Interfaces:**
- Consumes: existing PEP 621 `[project]` table and README development instructions.
- Produces: tested package metadata for project URLs, keywords, classifiers, explicit license inclusion, and end-user `pipx`/`pip` installation commands.

- [ ] **Step 1: Write failing metadata contract tests**

Create `tests/test_package_metadata.py` with focused tests that load
`pyproject.toml` via `tomllib` and assert:

- project name/version/Python remain `mcp-rig`, `0.1.0`, and `>=3.11`;
- `license-files` equals `['LICENSE']`;
- keywords include `mcp`, `testing`, `cli`, and `developer-tools`;
- classifiers contain Development Status 3 Alpha, Environment Console,
  Intended Audience Developers, OS Independent, Python 3, and Python
  3.11/3.12/3.13 entries;
- project URLs are exactly Repository and Issues under
  `https://github.com/gorkemgul/mcp-rig`; and
- README contains both `pipx install mcp-rig` and `pip install mcp-rig`, while
  no longer saying publication arrives later.

- [ ] **Step 2: Run the metadata tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_package_metadata.py -q`

Expected: FAIL because `license-files`, keywords, classifiers, project URLs,
and installation commands are absent.

- [ ] **Step 3: Add the exact PEP 621 metadata**

In `pyproject.toml`, add the fields required by Step 1 without adding an author,
changing version/dependencies, or adding the deprecated license classifier.
Use:

```toml
[project.urls]
Repository = "https://github.com/gorkemgul/mcp-rig"
Issues = "https://github.com/gorkemgul/mcp-rig/issues"
```

- [ ] **Step 4: Add end-user installation documentation**

Add an `Installation` section before development setup. Recommend `pipx` for
the CLI, present `pip` as the alternative, preserve source setup separately,
and remove the sentence that PyPI publication arrives later.

- [ ] **Step 5: Run the metadata tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_package_metadata.py -q`

Expected: all metadata contract tests pass.

- [ ] **Step 6: Build and inspect both distributions**

Run:

```bash
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Then inspect wheel `METADATA` and sdist `PKG-INFO` with the standard-library
`zipfile`/`tarfile` modules. Assert both contain the repository and issue URLs,
keywords, every classifier, `Requires-Python: >=3.11`, and license expression
`MIT`; assert `LICENSE` exists in both archives. Also assert `dist/` contains
exactly `mcp_rig-0.1.0-py3-none-any.whl` and `mcp_rig-0.1.0.tar.gz`.

Expected: Twine passes and every archive assertion succeeds.

- [ ] **Step 7: Run regression verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/python -m pip check && git diff --check`

Expected: all tests and lint pass, dependencies are consistent, and the diff
has no whitespace errors.

- [ ] **Step 8: Commit package metadata**

```bash
git add pyproject.toml README.md tests/test_package_metadata.py
git commit -m "build: add PyPI project metadata"
```

---

### Task 2: Shared Release Tag Validator

**Files:**
- Create: `scripts/check_release_tag.py`
- Create: `tests/test_release_tag.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `[project].version` from a caller-supplied `pyproject.toml` path and a raw GitHub Release tag string.
- Produces: `expected_tag(pyproject_path: Path) -> str`, `validate_release_tag(tag: str, pyproject_path: Path) -> None`, and `main(argv: Sequence[str] | None = None) -> int`; the workflow invokes `python scripts/check_release_tag.py "$RELEASE_TAG"`.

- [ ] **Step 1: Write failing validator tests**

In `tests/test_release_tag.py`, load `scripts/check_release_tag.py` with
`importlib.util.spec_from_file_location` and test:

- `expected_tag()` returns `v0.1.0` for the repository metadata;
- `validate_release_tag('v0.1.0', path)` returns normally;
- `validate_release_tag()` raises `ValueError` for `0.1.0`, `v0.1.1`, an empty
  string, and `release-v0.1.0`;
- the CLI exits 0 and prints the accepted tag for `v0.1.0`; and
- the CLI exits nonzero with a concise expected/received message for a mismatch.

- [ ] **Step 2: Run the validator tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_release_tag.py -q`

Expected: FAIL because `scripts/check_release_tag.py` does not exist.

- [ ] **Step 3: Implement the standard-library validator**

Create the three interfaces from the task block. Use `tomllib` and `Path`,
accept one positional tag and an optional `--pyproject` path defaulting to
`pyproject.toml`, print success only after validation, and convert validation or
file/TOML errors into a concise nonzero CLI result without a traceback.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_release_tag.py -q && .venv/bin/python scripts/check_release_tag.py v0.1.0`

Expected: all focused tests pass and the real repository tag check exits 0.

- [ ] **Step 5: Extend hosted lint coverage to the release script**

Update the existing CI workflow's lint command from `ruff check src tests` to
`ruff check src tests scripts`, so the new release utility is covered on every
supported Python version. Assert this exact command in
`tests/test_release_tag.py` by parsing `.github/workflows/ci.yml` with
`yaml.BaseLoader`.

- [ ] **Step 6: Run regression verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests scripts && .venv/bin/python -m pip check && git diff --check`

Expected: all tests and lint pass, dependencies are consistent, and the diff
has no whitespace errors.

- [ ] **Step 7: Commit the validator**

```bash
git add scripts/check_release_tag.py tests/test_release_tag.py .github/workflows/ci.yml
git commit -m "build: validate release tags against package version"
```

---

### Task 3: Trusted Publishing Workflow and Operator Guide

**Files:**
- Create: `.github/workflows/publish.yml`
- Create: `tests/test_publish_workflow.py`
- Create: `docs/releasing.md`

**Interfaces:**
- Consumes: Task 1 distribution metadata, Task 2 `scripts/check_release_tag.py`, GitHub Release tag context, and GitHub environment `pypi`.
- Produces: a `publish` workflow with isolated `build` and `publish` jobs plus exact setup/release instructions for the maintainer.

- [ ] **Step 1: Write failing workflow security tests**

Create `tests/test_publish_workflow.py` using `yaml.BaseLoader`. Assert:

- top-level trigger is exactly `release: {types: [published]}` and the literal
  `on` key survives parsing;
- workflow permissions equal only `{contents: read}`;
- both jobs use `github.event.release.prerelease == false`;
- concurrency is per release tag with cancellation disabled;
- `publish.needs == 'build'`, environment name is `pypi`, environment URL is
  `https://pypi.org/p/mcp-rig`, and publish permissions equal only
  `{id-token: write}`;
- every `uses` value contains a 40-character lowercase SHA and the approved
  action identities are checkout, setup-python, upload-artifact,
  download-artifact, and `pypa/gh-action-pypi-publish`;
- the publish job has exactly download and PyPA publish steps, with no `run`,
  checkout, setup, install, or repository execution step; and
- raw YAML contains no `secrets.`, `password`, `api-token`, `pull_request`,
  `workflow_dispatch`, `schedule`, `twine upload`, `test.pypi`,
  `skip-existing`, or `attestations: false`.

- [ ] **Step 2: Run the workflow tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_publish_workflow.py -q`

Expected: FAIL because `.github/workflows/publish.yml` does not exist.

- [ ] **Step 3: Create the release workflow security boundary**

Create `.github/workflows/publish.yml` with the exact architecture in the spec
and these reviewed immutable action pins:

```text
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1       # v7.0.1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97   # v7.0.0
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0 # v7.0.1
actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2
```

The build job must explicitly check out
`${{ github.event.release.tag_name }}` with `persist-credentials: false`, run
the shared tag validator before dependency installation, execute the existing
lint/test/dependency gates, build into an initially absent `dist/`, run Twine,
assert the exact two `0.1.0` filenames derived from `pyproject.toml`, smoke-test
the wheel in `$RUNNER_TEMP/mcp-rig-wheel`, and upload `dist/` as
`python-package-distributions` with `retention-days: 1` and
`if-no-files-found: error`.

The publish job downloads that artifact to `dist/` and invokes the pinned PyPA
action once with no inputs that weaken verification or attestations.

- [ ] **Step 4: Write the operator guide**

Create `docs/releasing.md` with:

- the exact pending PyPI publisher fields (`mcp-rig`, `gorkemgul`, `mcp-rig`,
  `publish.yml`, `pypi`);
- the requirement for a protected GitHub `pypi` environment with manual
  approval;
- preflight commands for tests, build, Twine, and the tag validator;
- the stable GitHub Release procedure using tag `v0.1.0` targeting `main`;
- verification of the Actions run and final PyPI page; and
- warnings that pending publishers do not reserve names, PyPI versions are
  immutable, and creating the release is the real publication trigger.

- [ ] **Step 5: Run focused workflow tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_publish_workflow.py tests/test_release_tag.py tests/test_package_metadata.py -q`

Expected: every focused test passes.

- [ ] **Step 6: Execute release-build equivalents locally**

Start from a clean `dist/`, then run:

```bash
.venv/bin/python scripts/check_release_tag.py v0.1.0
.venv/bin/ruff check src tests scripts
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Assert exactly one expected wheel and sdist. Create a fresh temporary virtual
environment, install only the wheel, run `mcp-rig --help`, and run the installed
`mcp-rig check` against the fixture using that environment's Python.

Expected: all commands exit 0 and the server smoke test reports `3/3 checks
passed` with the known nine advisory lint warnings.

- [ ] **Step 7: Run final regression verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests scripts && .venv/bin/python -m pip check && git diff --check`

Expected: all tests and lint pass, dependencies are consistent, and the diff
has no whitespace errors.

- [ ] **Step 8: Commit the release workflow**

```bash
git add .github/workflows/publish.yml tests/test_publish_workflow.py docs/releasing.md
git commit -m "ci: add trusted PyPI publishing workflow"
```

---

## Hosted Acceptance and Publication Boundary

After native execution and whole-branch review:

1. push `release/pypi-publishing` and open a PR without creating a tag or
   GitHub Release;
2. require the existing Python 3.11/3.12/3.13 and package checks to pass;
3. merge only after all hosted checks are green;
4. verify the GitHub `pypi` environment and pending PyPI Trusted Publisher with
   the exact values from `docs/releasing.md`;
5. stop and obtain explicit user confirmation before creating `v0.1.0`; and
6. after that confirmation, create the stable GitHub Release, wait through the
   environment approval and publish run, then verify installation from PyPI.

The implementation PR is complete at step 3. Steps 4–6 are the separately
authorized publication operation and must not be inferred from plan approval.
