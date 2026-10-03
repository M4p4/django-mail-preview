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

## Documentation builds

The Docs workflow asks Read the Docs to build the documentation: `latest` on every
push to `main`, and `stable` for every version tag after syncing the tags. It needs a
Read the Docs API token with access to the `django-mail-preview` project, stored as
the `RTD_TOKEN` repository secret. Without the secret the workflow only prints a
warning.
