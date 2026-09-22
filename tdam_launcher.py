"""PyInstaller entry point.

PyInstaller runs the spec's entry script as ``__main__`` with no package
context, so it can neither execute nor statically follow the relative imports
inside ``src/tdam/main.py`` (e.g. ``from .ui.splash import ...``). Importing the
package here gives those imports a parent package, and lets PyInstaller's
analysis traverse the full module graph.

Run from source: still use ``tdam`` (the ``[project.scripts]`` entry point) or
``python -m src.tdam.main`` — this file exists only for the frozen build.
"""

from tdam.main import main

if __name__ == "__main__":
    main()
