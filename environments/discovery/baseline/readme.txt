SERVICE   qa-docs-index   env: staging

a read-only reference service that serves reference questions
from a static documentation set, maintained by the docs team
for internal lookups.

layout:
- questions are drawn from the docs index and served one at a time
- responses are appended to a plain-text log for archival
- a caching layer sits in front of the index (15 min TTL)

owner: docs-platform@   oncall: #qa-docs
