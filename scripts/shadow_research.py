#!/usr/bin/env python3
"""Evaluate production and shadow configurations without an execution path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lyceum.shadow import ShadowHarness, ShadowStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--latest-batches", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(ShadowHarness(ShadowStore(args.database)).run(latest_batches=args.latest_batches), indent=2))


if __name__ == "__main__":
    main()
