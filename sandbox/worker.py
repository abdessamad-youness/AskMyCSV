"""Runs INSIDE the sandbox container. Executes the model-generated code.

The container is started with: --network none, read-only root, only the
uploaded CSV mounted read-only at /data/input.csv, output dir at /out.
This worker adds nothing: no keys, no env secrets, no extra access.

It pre-imports pandas as pd and matplotlib.pyplot as plt, exactly as the
code-generation prompt promises the model ("pandas is imported as pd,
matplotlib.pyplot as plt"), and passes both into the exec globals.
"""
import sys
import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CODE_PATH = "/work/code.py"


def main() -> int:
    with open(CODE_PATH) as f:
        code = f.read()
    try:
        exec(
            compile(code, "generated_code", "exec"),
            {"__name__": "__main__", "pd": pd, "plt": plt},
        )
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
