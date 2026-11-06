"""AskMyCSV — control app (runs on the Vultr VM, OUTSIDE the sandbox).

Flow: upload CSV + question -> Vultr Serverless Inference writes pandas
code -> code runs in the sandbox -> chart + table + the exact code return.
One automatic retry: a sandbox error is fed back to the model once.
"""
import base64
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .inference import generate_code
from .sandbox_runner import run_code

app = FastAPI(title="AskMyCSV")
BASE = Path(__file__).resolve().parent.parent
MAX_CSV_BYTES = 5 * 1024 * 1024


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
async def ask(file: UploadFile = File(...), question: str = Form(...)):
    data = await file.read()
    if len(data) > MAX_CSV_BYTES:
        return JSONResponse({"error": "CSV too large (max 5 MB)"}, status_code=413)

    with tempfile.TemporaryDirectory(prefix="askmycsv-upload-") as td:
        csv_path = Path(td) / "input.csv"
        csv_path.write_bytes(data)
        try:
            df = pd.read_csv(csv_path, nrows=5)
            full_cols = pd.read_csv(csv_path, nrows=0).columns.tolist()
        except Exception as e:
            return JSONResponse({"error": f"Could not read CSV: {e}"},
                                status_code=400)
        sample = df.to_string(index=False)

        code, source = await generate_code(question, full_cols, sample)
        run = run_code(code, csv_path)
        retried = False
        if run["exit_code"] != 0:
            retried = True
            code, source = await generate_code(
                question, full_cols, sample,
                previous_error=run["stderr"] or run["stdout"])
            run = run_code(code, csv_path)

    return {
        "question": question,
        "code": code,
        "code_source": source,          # 'vultr' or 'fallback'
        "sandbox_mode": run["mode"],    # 'docker' in production
        "retried": retried,
        "exit_code": run["exit_code"],
        "stdout": run["stdout"],
        "stderr": run["stderr"],
        "result_csv": run["result_csv"],
        "chart_png_base64": base64.b64encode(run["chart_png"]).decode()
        if run["chart_png"] else None,
    }
