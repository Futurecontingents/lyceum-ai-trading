#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  echo "Missing machine-local .env; judging service will not start." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "${LYCEUM_ALPACA_PROFILE:-}" != "judging" ]]; then
  echo "Refusing to start: LYCEUM_ALPACA_PROFILE must be judging." >&2
  exit 2
fi
if [[ -z "${LYCEUM_EXPECTED_ACCOUNT_ID:-}" ]]; then
  echo "Refusing to start: LYCEUM_EXPECTED_ACCOUNT_ID must pin the judging API account." >&2
  exit 2
fi
if [[ "${ALPACA_TRADING_BASE_URL:-}" != "https://paper-api.alpaca.markets" ]]; then
  echo "Refusing to start: only the Alpaca paper endpoint is permitted." >&2
  exit 2
fi

actual_account_id="$(alpaca --profile judging account get --jq '.id' | tr -d '"')"
if [[ "$actual_account_id" != "$LYCEUM_EXPECTED_ACCOUNT_ID" ]]; then
  echo "Refusing to start: judging profile does not match the pinned API account." >&2
  exit 2
fi

doctor_output="$(alpaca --profile judging doctor)"
if [[ "$doctor_output" != *"Trading:  https://paper-api.alpaca.markets"* ]]; then
  echo "Refusing to start: judging profile did not verify the paper endpoint." >&2
  exit 2
fi

case "${1:-service}" in
  --read-only-rehearsal)
    export LYCEUM_EXECUTION_MODE=READ_ONLY
    export LYCEUM_ENABLE_PAPER_ORDERS=false
    .venv/bin/python -m lyceum doctor
    exec .venv/bin/python -m lyceum run --once --read-only-rehearsal
    ;;
  --service|--manual)
    .venv/bin/python -m lyceum doctor
    exec /usr/bin/caffeinate -s .venv/bin/python -m lyceum run
    ;;
  *)
    echo "Usage: $0 [--service|--manual|--read-only-rehearsal]" >&2
    exit 2
    ;;
esac
