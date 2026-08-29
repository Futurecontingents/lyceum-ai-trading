#!/usr/bin/env bash
set -euo pipefail

python -m lyceum doctor
python -m lyceum run --once --demo

