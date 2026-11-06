"""Runs INSIDE the sandbox container. Executes the model-generated code.

The container is started with: --network none, read-only root, only the
uploaded CSV mounted read-only at /data/input.csv, output dir at /out.
This worker adds nothing: no keys, no env secrets, no extra access.
"""
import sys
import traceback

CODE_PATH = "/work/code.py"


def main() -> int:
    with open(CODE_PATH) as f:
        code = f.read()
    try:
        exec(compile(code, "generated_code", "exec"), {"__name__": "__main__"})
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
