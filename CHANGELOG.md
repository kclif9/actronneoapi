# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Strict typing** — added `py.typed` marker (PEP 561) so downstream consumers get
  inline type information out of the box.
- **`_version.py`** — single-source version module (`actron_neo_api.__version__`)
  using `importlib.metadata` to stay in sync with the built distribution.
- **CHANGELOG.md** — this file.

### Changed

- **Modernised build** — migrated from `setuptools`/`requirements.txt` to
  `hatchling` + `hatch-vcs` with a `uv`-compatible `pyproject.toml`.
  Removed legacy `setup.py`, `requirements.txt`.
- **CI workflow** — updated `publish.yml` to use `python -m build` instead of
  `setup.py sdist bdist_wheel`, and bumped action versions.

### Removed

- `setup.py` — no longer needed with `hatchling`.
- `requirements.txt` — dependencies are declared in `pyproject.toml`.
