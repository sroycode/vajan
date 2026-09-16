#!/usr/bin/env python3
"""
run.py
------
Universal entrypoint for Vajan:
- Defaults to the Vast.ai CLI (`vajan.py`).
- On the remote GPU instance, if invoked with `--input / -i`, routes to `run_engine.py`.
"""

import sys

if __name__ == "__main__":
    if "--input" in sys.argv or "-i" in sys.argv:
        from run_engine import main as engine_main
        engine_main()
    else:
        from vajan import main as vajan_main
        vajan_main()
