#!/bin/bash
set -euo pipefail
LCARS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$LCARS_DIR/scripts/manage.py" "$@"
