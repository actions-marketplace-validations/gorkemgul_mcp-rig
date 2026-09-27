# MCP Rig CI and Package Validation Design

## Purpose

Make every proposed change prove that MCP Rig works across its supported Python
versions and that the repository can produce an installable distribution. The
workflow must exercise the public CLI, not only unit tests, so failures in
packaging, entry points, examples, or stdio process startup are caught before a
release.

This increment establishes quality and distribution gates. It does not publish
to PyPI, create tags or GitHub Releases, or require repository secrets.

## Scope

This increment adds:

- a GitHub Actions workflow for pull requests and pushes to `main`;
- Python 3.11, 3.12, and 3.13 test-matrix coverage on Ubuntu;
- Ruff, pytest, dependency consistency, and public CLI dogfood checks;
- wheel and source-distribution construction;
- package metadata validation with Twine;
- installation of the built wheel into a fresh virtual environment;
- a wheel-installed `mcp-rig check` smoke test; and
- a portable checked-in example that works in CI and in an activated local
  virtual environment.

The following remain out of scope:

- uploading distributions to PyPI or TestPyPI;
- PyPI trusted-publisher configuration, API tokens, or repository secrets;
- version changes, tags, changelog generation, and GitHub Releases;
- Windows, macOS, PyPy, free-threaded Python, or Python prerelease coverage;
- coverage thresholds or third-party coverage services;
- dependency locking, Dependabot, or scheduled dependency testing; and
- artifact retention or download from GitHub Actions.

## Workflow Triggers and Security

The workflow is named `ci` and runs on:

- every pull request; and
- pushes to `main`.

It declares workflow-level `contents: read` permissions. No job receives write
permissions, environment access, OIDC tokens, or repository secrets. It uses
the ordinary `pull_request` event, never `pull_request_target`, because the
workflow installs and executes code from the proposed revision.

Concurrency groups use workflow name plus pull-request number or Git ref.
Superseded runs on the same pull request or branch are cancelled so only the
latest revision consumes runner time.

The workflow uses current official major versions `actions/checkout@v7` and
`actions/setup-python@v7`. Third-party actions are not introduced.

## Test Matrix Job

The `test` job runs on `ubuntu-latest` with `fail-fast: false` across Python
`3.11`, `3.12`, and `3.13`. Each matrix entry:

1. checks out the proposed revision;
2. installs the selected Python and enables pip caching against
   `pyproject.toml`;
3. upgrades pip;
4. installs the project editable with `.[dev]`;
5. runs `ruff check src tests`;
6. runs `pytest -q`;
7. runs `python -m pip check`;
8. runs `mcp-rig run examples/fixture.yaml --junit report.xml`; and
9. runs `mcp-rig check "python tests/fixtures/fixture_server.py"`.

The matrix intentionally dogfoods both public subcommands. The suite command
also proves that JUnit writing works in the hosted runner. The check command
runs without `--strict` because fixture lint warnings are deliberate test data;
protocol failures still fail the step.

No test result is uploaded in this increment. The job log and exit status are
the gate; artifact retention can be added only when a consumer needs it.

## Distribution Job

The `package` job depends on the complete test matrix and runs once on
`ubuntu-latest` with Python 3.13. It:

1. checks out the same revision;
2. installs Python and enables pip caching;
3. upgrades pip and installs `build` and `twine`;
4. runs `python -m build` to create one wheel and one source distribution;
5. runs `python -m twine check dist/*`;
6. creates a fresh virtual environment outside the repository;
7. installs the built wheel into that environment; and
8. uses the wheel-installed `mcp-rig` and that environment's Python to check
   the deterministic fixture server.

The smoke command must report `3/3 checks passed` and exit 0. Installing the
wheel rather than the source tree proves package discovery, runtime
dependencies, and the console-script entry point. The source distribution is
metadata-checked but is not installed separately; wheel and sdist construction
share the same Hatchling configuration.

The distribution files are ephemeral runner output. Uploading them as Actions
artifacts is intentionally excluded because this is validation, not a release
pipeline.

## Portable Example Contract

`examples/fixture.yaml` currently launches `../.venv/bin/python`, which assumes
a repository-local Unix virtual environment. The example changes to invoke
`python` from `PATH` while retaining a suite-relative fixture path:

```yaml
server: python ../tests/fixtures/fixture_server.py
```

CI's selected Python is on `PATH`, so the example uses the environment where
MCP Rig and its dependencies were installed. Local documentation is updated to
activate `.venv` before invoking example commands; this makes the same contract
explicit for developers and removes the Unix-only executable path from YAML.

The existing suite loader continues resolving the fixture path relative to the
YAML file. No parser, client, or runner behavior changes.

## Local Validation and Configuration Testing

The change is workflow configuration plus documentation/example portability;
it does not add production Python behavior. Instead of inventing unit tests for
GitHub's workflow engine, validation uses the real commands the workflow will
execute:

- Ruff, pytest, and pip dependency checks in the development environment;
- both public CLI dogfood commands;
- local wheel and sdist construction plus Twine metadata checking;
- a fresh-environment wheel smoke test; and
- the actual GitHub Actions run created by the pull request.

Before push, the workflow file is parsed as YAML and inspected for the exact
trigger, permissions, version matrix, dependency chain, and commands. The PR is
not mergeable by process until every matrix entry and the package job complete
successfully. If GitHub rejects the workflow syntax or a hosted runner exposes
an environment-specific failure, the job logs are the authoritative failure
evidence and the fix is committed to the same branch.

## Architecture and File Changes

### `.github/workflows/ci.yml`

Own triggers, read-only permissions, concurrency, the Python test matrix, the
dependent package job, and all hosted-runner commands. It contains no publish
step and references no secrets.

### `examples/fixture.yaml`

Replace the repository-local interpreter path with the active `python` from
`PATH`. Keep all test cases and expectations unchanged.

### `README.md`

Make virtual-environment activation explicit in development setup and use the
installed `mcp-rig` command in examples. Document that the repository CI tests
Python 3.11 through 3.13 and validates built distributions without publishing
them.

No Python source modules or runtime dependency declarations change.

## Failure Semantics

- Any failed matrix entry fails the workflow, even if other Python versions
  pass; `fail-fast: false` preserves evidence from every supported version.
- The package job does not start unless all matrix entries pass.
- Ruff, pytest, dependency, dogfood, build, Twine, install, and wheel smoke
  commands rely on their native non-zero exit codes.
- JUnit output is a side effect of dogfooding and not a substitute for the
  command exit status.
- A cancelled superseded run is not a quality result; the newest run must
  complete successfully.

## Success Criteria

The increment is complete when:

- the workflow is valid and visible on the pull request;
- Python 3.11, 3.12, and 3.13 each pass lint, tests, dependency checks, and both
  public CLI dogfood commands;
- the package job builds wheel and sdist, passes Twine validation, installs the
  wheel in a clean environment, and reports `3/3 checks passed`;
- the example suite no longer depends on a repository-local `.venv` path;
- the workflow uses read-only permissions and no secrets; and
- the PR is merged only after the full GitHub Actions run is green.
