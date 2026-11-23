"""Run with python -m backend.cli."""

import argparse
import logging
from pathlib import Path

from .db import connect, ingest, initialize
from .metrics import summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Load a freight CSV and print headline metrics.')
    parser.add_argument('csv', nargs='?', type=Path)
    parser.add_argument('--mode', choices=('replace', 'append'), default='replace')
    parser.add_argument('--grace', choices=range(4), type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    initialize()
    with connect() as conn:
        if args.csv:
            ingest(conn, args.csv.read_bytes(), args.csv.name, args.mode)
        result = summary(conn, args.grace)
    pct = result['on_time_pct']
    print(f"Unique shipments: {result['unique_shipments']:,}")
    print(f"On-time (+{args.grace} days): {str(pct) + '%' if pct is not None else 'n/a'}")
    print(f"Valid deliveries: {result['valid_deliveries']:,} | Excluded deliveries: {result['delivered_excluded']:,}")
    print(f"Total weight: {result['total_weight_tonnes']:,.3f} tonnes | Excluded weights: {result['weight_excluded']:,}")
    for lane in result['top_lanes']:
        print(f"{lane['lane']}: {lane['count']:,}")


if __name__ == '__main__':
    main()
