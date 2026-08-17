# Purpose: Print the exact nuke.pluginAddPath(...) line for this checkout (artist install helper).

from __future__ import print_function

import os
import sys


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    ).replace("\\", "/")
    line = 'nuke.pluginAddPath("%s")' % root
    print("# Add this line to ~/.nuke/init.py (install ROOT, not the inner nuke/ folder):")
    print(line)
    print("# Studio alternative: set NUKE_PATH to that same folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
