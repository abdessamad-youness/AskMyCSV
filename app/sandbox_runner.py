"""Runs generated code with blast radius zero.

Production (on the Vultr VM): a fresh Docker container per request with
  --network none            no internet, no calls home
  --read-only               container filesystem cannot be changed
  -v <csv>:/data/input.csv:ro   ONLY the uploaded CSV, read-only
  --memory 256m --cpus 0.5  hard resource caps
  timeout 30s, container removed (--rm) after the run
  no environment variables / API keys are passed in

Local dev (no Docker installed): falls back to a subprocess in a temp dir
with a timeout and a scrubbed environment. This mode is for development
only and is clearly reported in the result.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 30
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "askmycsv-sandbox")


def _read_outputs(out_dir: Path) -> dict:
    result = {"stdout": "", "stderr": "", "exit_code": None,
              "chart_png": None, "result_csv": None, "mode": ""}
    chart = out_dir / "chart.png"
    if chart.exists():
        result["chart_png"] = chart.read_bytes()
    table = out_dir / "result.csv"
    if table.exists():
        result["result_csv"] = table.read_text(errors="replace")[:8000]
    return result


def run_code(code: str, csv_path: Path) -> dict:
    csv_path = Path(csv_path).resolve()
    work = Path(tempfile.mkdtemp(prefix="askmycsv-"))
    out_dir = work / "out"
    out_dir.mkdir()
    code_path = work / "code.py"
    code_path.write_text(code)
    try:
        if shutil.which("docker"):
            return _run_docker(code, csv_path, work, out_dir)
        return _run_local(code_path, csv_path, work, out_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_docker(code: str, csv_path: Path, work: Path, out_dir: Path) -> dict:
    code_file = work / "gen_code.py"
    code_file.write_text(code)
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--memory", "256m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "-v", f"{csv_path}:/data/input.csv:ro",
        "-v", f"{code_file}:/work/code.py:ro",
        "-v", f"{out_dir}:/out",
        "--tmpfs", "/tmp:size=64m",
        SANDBOX_IMAGE,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=TIMEOUT_SECONDS)
    result = _read_outputs(out_dir)
    result.update(stdout=proc.stdout[:8000], stderr=proc.stderr[-4000:],
                  exit_code=proc.returncode, mode="docker")
    return result


def _run_local(code_path: Path, csv_path: Path, work: Path, out_dir: Path) -> dict:
    """DEV ONLY: same worker logic, no Docker isolation. Never use in prod."""
    runner = work / "local_runner.py"
    runner.write_text(
        "import pathlib, sys\n"
        f"code = pathlib.Path({str(code_path)!r}).read_text()\n"
        "code = code.replace('/data/input.csv', " + repr(str(csv_path)) + ")\n"
        "code = code.replace('/out/', " + repr(str(out_dir) + "/") + ")\n"
        "exec(compile(code, 'generated_code', 'exec'), {'__name__': '__main__'})\n"
    )
    clean_env = {"PATH": os.environ.get("PATH", ""), "HOME": str(work),
                 "MPLBACKEND": "Agg"}
    try:
        proc = subprocess.run([sys.executable, str(runner)],
                              capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, env=clean_env, cwd=work)
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        exit_code, stdout = 124, (e.stdout or b"").decode(errors="replace")
        stderr = "Timed out after 30 seconds."
    result = _read_outputs(out_dir)
    result.update(stdout=stdout[:8000], stderr=stderr[-4000:],
                  exit_code=exit_code, mode="local-dev (NO isolation)")
    return result
