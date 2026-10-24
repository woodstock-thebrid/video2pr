#!/usr/bin/env bash
set -euo pipefail
python3 -m uvicorn backend.main:app --reload --port 8000
