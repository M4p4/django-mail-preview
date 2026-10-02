# Contributing

Thanks for helping out. Clone the repository, run `uv sync` to install the test
dependencies, then `uv run pytest`.

To run the tests against every supported Python and Django version, as CI does,
use `uvx --with tox-uv tox run-parallel`. Coverage must stay at 100% across the
combined matrix: `uv run coverage combine && uv run coverage report`.
