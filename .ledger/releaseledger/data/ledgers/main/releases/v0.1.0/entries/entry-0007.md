---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0007
release_version: v0.1.0
kind: internal
summary:
  Changed repository automation to dedicated test, lint, coverage, pre-commit,
  and publishing workflows
status: accepted
audience: null
scopes: []
source_refs:
  - git:8a0ae0f5b37d3273abbc3034557a3b435a82c5da
paths:
  - .github/workflows/codecov.yml
  - .github/workflows/pre-commit.yml
  - .github/workflows/python-publish.yml
  - .github/workflows/tests.yml
issues: []
prs: []
sources:
  - git:8a0ae0f5b37d3273abbc3034557a3b435a82c5da
contributors:
  - "@holgern"
breaking: false
internal: true
order: 7
---
