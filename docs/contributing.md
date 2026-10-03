# Contributing

Bug reports and pull requests are welcome on
[GitHub](https://github.com/M4p4/django-mail-preview). For a larger change, open an
issue first so we can agree on the approach.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). Clone the repository and run the
tests:

```console
$ git clone https://github.com/M4p4/django-mail-preview.git
$ cd django-mail-preview
$ uv run pytest
```

`uv run` creates a virtual environment with the test dependencies and Django 5.2 on
first use.

## Checks

Every pull request has to pass the same checks as CI.

[pre-commit](https://pre-commit.com/) runs the linters, formatters and mypy. Install
the hooks once, or run them on every file:

```console
$ uvx --with pre-commit-uv pre-commit install
$ uvx --with pre-commit-uv pre-commit run --all-files
```

[tox](https://tox.wiki/) runs the tests on every supported Python and Django version,
and builds the docs:

```console
$ uvx --with tox-uv tox                   # everything
$ uvx --with tox-uv tox -e py314-django61 # one environment
$ uvx --with tox-uv tox -e docs           # the docs
```

Coverage must stay at 100%, branches included. Tox environments need the matching
Python versions; `uv python install 3.10 3.11 3.12 3.13 3.14` gets them all.

When a change affects users, add a line under `## Unreleased` in `CHANGELOG.md`, and
update the docs page for the feature.

## Trying it in a project

The test suite covers the package, but the pages are best judged in a browser. A
throwaway project is enough: `django-admin startproject`, the three lines from the
[quickstart](index.md#quickstart), a `previews.py` in an app, and a few messages sent
from `manage.py shell`.

## Releases

Releases are published to PyPI by the CI workflow when a version tag is pushed. To
make one:

1. In a pull request, set the new version in `pyproject.toml`, rename the entries
   under `## Unreleased` in `CHANGELOG.md` to a `## X.Y.Z (YYYY-MM-DD)` section with
   an empty `## Unreleased` heading kept on top, and run `uv lock` so the lock file
   carries the new version.
2. After the merge, tag the merge commit on `main` with the bare version and push the
   tag:

   ```console
   $ git switch main && git pull
   $ git tag 0.1.0
   $ git push origin 0.1.0
   ```

CI runs every check on the tag. When they all pass, the Release job waits for a
maintainer to approve the `release` environment, makes sure the tag matches the version
in the built wheel, and publishes the same files to PyPI with
[trusted publishing](https://docs.pypi.org/trusted-publishers/). Nothing is rebuilt,
and no PyPI token is stored in the repository. The Docs workflow then builds `stable`
from the new tag.

## Documentation builds

The Docs workflow asks Read the Docs to build the documentation: `latest` on every
push to `main`, and `stable` for every version tag after syncing the tags. It needs a
Read the Docs API token with access to the `django-mail-preview` project, stored as
the `RTD_TOKEN` repository secret. Without the secret the workflow only prints a
warning.
