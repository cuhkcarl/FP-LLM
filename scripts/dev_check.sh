# scripts/dev_check.sh
#!/usr/bin/env bash
set -euo pipefail
pre-commit run -a || true
git add -A
pre-commit run -a
ruff check .
black --check .
isort --check-only .
mypy src
pytest -q
echo "✅ dev check all green"
