#!/usr/bin/env python3
"""Convenience wrapper so the tool can be run as `python run.py ...`.

    python run.py --protocol sample-a-test-protocol-nv-200.pdf \
                  --report   sample-b-verification-report-nv-200.pdf
"""

from protocolqc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
