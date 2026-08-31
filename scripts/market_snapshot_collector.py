#!/usr/bin/env python3
"""Collect one append-only, market-hours shadow snapshot batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lyceum.shadow import MarketCollector, ReadOnlyAlpaca, ShadowStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="judging")
    parser.add_argument("--database", type=Path, default=Path("data/shadow_market.db"))
    args = parser.parse_args()
    result = MarketCollector(ShadowStore(args.database), ReadOnlyAlpaca(args.profile)).collect_once()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
