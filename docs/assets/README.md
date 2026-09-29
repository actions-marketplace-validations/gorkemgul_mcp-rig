# README artwork

The banner and terminal demo use black and white foundations, a subtle purple
background tint, and restrained cyan highlights. The animation uses output captured
from the local CLI, including its measured timings; it types commands and reveals
that captured output at a readable pace.

To regenerate, install Pillow in an artwork environment and run from a development
checkout with MCP Rig installed:

```bash
python -m pip install Pillow
python scripts/render_readme_assets.py
```

The renderer uses the checkout's `.venv/bin/python` for CLI commands when available,
otherwise its own interpreter. It uses Menlo and Arial on macOS, or DejaVu Sans
and DejaVu Sans Mono on Linux. All demo commands must succeed, and the generated
JUnit report is checked for three passing tests before rendering. The temporary
report is removed afterwards.

- `banner.png`: README banner, with transparent rounded corners.
- `cli-demo.gif`: looping demo of suites, tag selection, and JUnit export.
- `cli-demo-poster.png`: still frame for previews and environments without animation.

The README uses repository-relative image paths, which work in local previews
and on the private GitHub repository. PyPI cannot access these private assets;
public image hosting is needed to display them there.

CI uses GitHub's native workflow badge for `ci.yml` on `main`. PyPI version,
Python versions, and monthly downloads are live Shields.io badges. The download
provider may temporarily rate limit requests. MIT is the repository's declared
license. Issues and stars are navigation badges while the repository is private;
Shields.io cannot read private repository counts. Once the repository is public,
they can use `/github/issues/gorkemgul/mcp-rig` and `/github/stars/gorkemgul/mcp-rig`.
