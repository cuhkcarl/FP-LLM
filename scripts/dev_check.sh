# scripts/dev_check.sh
#!/usr/bin/env bash
set -euo pipefail
ruff check .
black --check .
isort --check-only .
mypy src
pytest -q
echo "✅ dev check all green"
