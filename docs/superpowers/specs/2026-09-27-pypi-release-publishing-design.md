# MCP Rig PyPI Release Publishing Design

## Status

Approved in-chat design, written for review before implementation planning.

## Intent

Publish MCP Rig as `mcp-rig` on PyPI without storing a PyPI password or API
token in GitHub. A maintainer should be able to publish a reviewed version by
creating a stable GitHub Release whose tag matches the version in
`pyproject.toml`. The release must rebuild and verify its own distributions,
pause at a protected GitHub environment, and then authenticate to PyPI through
Trusted Publishing.

The first target is `v0.1.0`. The workflow and metadata must remain suitable
for later releases without embedding that version in workflow logic.

## Current State

- The distribution name and console command are both `mcp-rig`.
- `pyproject.toml` contains version `0.1.0`, an MIT license declaration, a
  README, Python `>=3.11`, runtime dependencies, and the Hatchling build
  backend.
- CI tests Python 3.11, 3.12, and 3.13; builds wheel and source distributions;
  runs Twine metadata checks; and smoke-tests the wheel in a clean environment.
- The PyPI JSON endpoint for `mcp-rig` returned HTTP 404 during design work on
  2026-09-27. This indicates that no public project was visible at that time,
  but it does not reserve the name.
- No PyPI credentials, Trusted Publisher, GitHub `pypi` environment, release
  workflow, or GitHub Release exists yet.

## Chosen Release Model

Use a dedicated workflow at `.github/workflows/publish.yml`, triggered only by
the `published` event for a stable GitHub Release. This is preferred over a raw
tag-push workflow because the release page gives the maintainer a deliberate,
reviewable publication action and supports release notes before deployment.

The workflow will reject prereleases and will not expose `workflow_dispatch`,
branch, pull-request, or scheduled publishing paths. Publishing from a local
Twine command is outside the supported release path.

Two jobs keep build code outside the OIDC trust boundary:

1. `build` checks out the release tag, verifies tag/version consistency, runs
   the quality gates, builds and checks the distributions, smoke-tests the
   wheel, and uploads only the completed `dist/` directory as a short-lived
   GitHub Actions artifact.
2. `publish` depends on `build`, downloads that artifact, and invokes the
   official PyPA publish action. It performs no checkout, build, dependency
   installation, or arbitrary repository script execution.

## Trigger and Version Contract

The workflow consumes `github.event.release.tag_name` and explicitly checks out
that tag. Only stable releases are eligible: both jobs require
`github.event.release.prerelease == false`, and drafts cannot emit the
`published` event.

The release tag must have the form `v<project-version>`. A small standard-library
Python check reads `[project].version` from `pyproject.toml` with `tomllib` and
fails unless the tag is exactly `v` followed by that version. For the first
release, the only accepted tag is therefore `v0.1.0`.

The workflow will use a per-tag concurrency group and will not cancel an
in-progress publication. PyPI versions are immutable, so it will not enable
`skip-existing`; duplicate or inconsistent publication attempts must fail
loudly.

## Permissions and Supply-Chain Boundary

Workflow-level permissions are `contents: read`. The `build` job receives no
additional permission. The `publish` job overrides permissions with only
`id-token: write`, the capability required for PyPI Trusted Publishing.

The `publish` job uses the GitHub environment `pypi` with the project URL
`https://pypi.org/p/mcp-rig`. The repository environment must require manual
approval before deployment. No password, PyPI token, repository secret, or
long-lived credential is permitted.

Repository-owned scripts never execute in the OIDC-enabled job. Build and
publish remain separate jobs connected only by a named distribution artifact.
Official GitHub artifact actions transfer the files. Every external action,
including the PyPA publish action, is pinned to the immutable full commit for
its reviewed stable release, with the human-readable release version in a
comment. The exact commits will be resolved from their signed stable tags
during implementation.

Trusted Publishing produces PyPI attestations by default; the workflow will
not disable them.

## Package Metadata

`pyproject.toml` will retain the existing name, version, dependency bounds,
Python requirement, CLI entry point, build backend, and license expression. It
will add:

- `license-files = ["LICENSE"]` so the distribution contents are explicit;
- keywords for MCP, testing, CLI, and developer tooling;
- classifiers for alpha development status, console use, developers, OS
  independence, Python 3, and supported Python 3.11–3.13 versions; and
- project URLs for the repository and issue tracker.

No author email or organization identity will be invented. No dependency,
Python support, CLI behavior, or version changes are part of this increment.

README installation documentation will add:

- `pipx install mcp-rig` as the recommended isolated CLI installation;
- `pip install mcp-rig` as the standard package installation alternative; and
- a concise source-development setup that remains separate from end-user
  installation.

The statement that PyPI publication arrives later will be removed and replaced
with the end-user installation commands. After successful publication, a small
follow-up may add the live PyPI project link if it is not already predictable
from the package name.

## Build Job

The build job runs on `ubuntu-latest` with Python 3.13 and performs these steps:

1. Check out the exact GitHub Release tag with persisted Git credentials
   disabled.
2. Verify the `v<version>` tag contract.
3. Install the project development extras plus `build` and `twine`.
4. Run Ruff, the complete pytest suite, and `pip check`.
5. Build exactly one wheel and one source distribution.
6. Run `twine check` on both files.
7. Create a fresh virtual environment, install only the built wheel, run
   `mcp-rig --help`, and run `mcp-rig check` against the fixture server using
   the fresh environment's Python interpreter.
8. Upload the two files as a named artifact with a short retention period and
   fail if no files are found.

The job will assert the expected normalized filenames for the project version,
preventing stale or extra distributions from entering the artifact.

## Publish Job

The publish job:

- depends on the successful build job;
- runs only for a stable published release;
- declares the protected `pypi` environment;
- receives only `id-token: write` permission;
- downloads the named distribution artifact into `dist/`; and
- invokes the SHA-pinned `pypa/gh-action-pypi-publish` action once.

It will not check out the repository, install packages, run shell scripts,
publish to TestPyPI, attach assets to the GitHub Release, or tolerate existing
files. TestPyPI is omitted because the existing clean-wheel gate already tests
installation and because a second index adds account setup and versioning
complexity without improving the first stable pure-Python release materially.

## External Setup Boundary

Workflow implementation and merge can be completed without PyPI credentials.
Actual publication requires two account-level configurations that cannot be
proved by repository tests:

1. In GitHub, create the `pypi` environment and require manual deployment
   approval.
2. In the PyPI account, register a pending GitHub Trusted Publisher with:
   - PyPI project name: `mcp-rig`
   - GitHub owner: `gorkemgul`
   - repository: `mcp-rig`
   - workflow: `publish.yml`
   - environment: `pypi`

A pending publisher does not reserve the name. These settings must be completed
before publishing the first GitHub Release.

Creating the `v0.1.0` GitHub Release is the irreversible publication trigger
and requires a separate explicit user confirmation after the workflow is
merged and both external settings are verified.

## Validation Strategy

Repository validation will cover configuration and package boundaries without
contacting PyPI:

- parse workflow YAML with `yaml.BaseLoader` to preserve the literal `on` key;
- assert the only workflow event is GitHub Release publication and every job
  rejects prereleases;
- assert build/publish job dependency and exact job-level permissions;
- reject secrets, passwords, token inputs, TestPyPI, local Twine upload, broad
  write permissions, extra triggers, and `skip-existing`;
- assert the publish job contains no checkout, package installation, build, or
  repository shell execution;
- assert every action reference is approved and pinned to a full commit SHA;
- test accepted and rejected tag/version pairs through the same comparison
  logic used by the workflow;
- build wheel and sdist, inspect their metadata and contents, and run Twine;
- install the wheel into a fresh environment and run the public CLI; and
- run the complete existing test/lint/dependency suite.

The pull request's hosted Actions result remains a required merge gate. The
release workflow itself cannot authenticate to PyPI safely during pull-request
testing, so its first end-to-end OIDC proof is the manually approved `v0.1.0`
release run.

## Failure Handling

- A malformed or mismatched tag fails before build or artifact upload.
- Test, lint, metadata, package-count, or wheel-smoke failures prevent the
  publish job from becoming eligible.
- Missing environment approval leaves the publish job waiting without exposing
  an OIDC token.
- Missing or incorrect Trusted Publisher configuration makes PyPI reject the
  publish job; no token fallback is allowed.
- A package-name race or duplicate version causes a loud publication failure.
- If files reached PyPI before a later step failed, the version is treated as
  published and immutable; it is never overwritten. A correction requires a
  new version.

## Non-Goals

- TestPyPI publication
- automatic semantic versioning or changelog generation
- publishing on every tag or branch push
- local credential-based upload
- GitHub Release asset attachment
- signing outside PyPI's default Trusted Publishing attestations
- changing runtime behavior, dependencies, Python support, or version

## Acceptance Criteria

- Package metadata is complete enough for a useful PyPI project page and is
  present in both wheel and source distribution.
- End users have clear `pipx` and `pip` installation instructions.
- A stable GitHub Release with a matching `v<version>` tag builds one wheel and
  one sdist, verifies both, and gates publication behind the `pypi` environment.
- Only the publish job can request an OIDC token, and it executes no repository
  code.
- No PyPI secret or long-lived credential exists in repository configuration.
- The first real upload occurs only after explicit user confirmation and
  successful external Trusted Publisher/environment setup.

## References

- PyPI Trusted Publisher project creation:
  <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>
- PyPA GitHub Actions publication guide:
  <https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
- PyPA publish action:
  <https://github.com/pypa/gh-action-pypi-publish>
