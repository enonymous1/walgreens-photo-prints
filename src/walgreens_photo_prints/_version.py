"""Package version, single source of truth.

``pyproject.toml`` reads this via ``tool.setuptools.dynamic``; the
package ``__init__`` and the CLI import it from here. Never duplicate
the version string in another file.
"""

__version__ = "1.3.0"
