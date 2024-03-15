# datasette-export-database

[![PyPI](https://img.shields.io/pypi/v/datasette-export-database.svg)](https://pypi.org/project/datasette-export-database/)
[![Changelog](https://img.shields.io/github/v/release/datasette/datasette-export-database?include_prereleases&label=changelog)](https://github.com/datasette/datasette-export-database/releases)
[![Tests](https://github.com/datasette/datasette-export-database/actions/workflows/test.yml/badge.svg)](https://github.com/datasette/datasette-export-database/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/datasette/datasette-export-database/blob/main/LICENSE)

Export a copy of a SQLite database on demand

## Installation

Install this plugin in the same environment as Datasette.
```bash
datasette install datasette-export-database
```
## Usage

Users with the `export-database` permission will be able to download a fresh snapshot of any on-disk (not in-memory) database using a new option in the database action menu.

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:
```bash
cd datasette-export-database
python3 -m venv venv
source venv/bin/activate
```
Now install the dependencies and test dependencies:
```bash
pip install -e '.[test]'
```
To run the tests:
```bash
pytest
```
