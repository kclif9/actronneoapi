"""Version information for actron-neo-api."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("actron-neo-api")
except PackageNotFoundError:
    # Fallback for environments where the package metadata is unavailable
    # (e.g. editable installs without build isolation).
    __version__ = "0.0.0"
