# Development

Install contributor dependencies:

```bash
pip install -e '.[dev,docs]'
```

Run the offline quality checks:

```bash
python -m compileall pyjev examples docs
pytest
ruff check .
python docs/make.py html
python docs/make.py linkcheck
python -m build
twine check dist/*
```

Tests use fake or injected SDK clients and do not require a live API key. Versions are
derived from Git tags by `setuptools-scm`; `_version.py` is generated in build contexts.
Release history is owned by releaseledger and rendered into the changelog page.

Documentation examples that would call Jev are illustrative code blocks. Executable
checks should use pure parsing/validation or injected fakes; documentation builds must
never call the live API.
