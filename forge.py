"""
Funscript Forge — entry point.

Built on the funscript-tools processing engine by edger477:
  https://github.com/edger477/funscript-tools

All processing algorithms and transforms are their work.
This file launches the Forge workflow UI.
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ui.forge_window import main

if __name__ == "__main__":
    def log_exception(exc_type, exc_value, exc_traceback):
        with open("forge.log", "a") as f:
            f.write(f"--- {datetime.now()} ---\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            f.write("\n")
        print(f"Unhandled error — see forge.log", file=sys.stderr)

    sys.excepthook = log_exception
    main()
