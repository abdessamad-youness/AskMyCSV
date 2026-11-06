"""Vultr Serverless Inference client + offline fallback code generator.

The model only ever sees the question + column names + a few sample rows.
It never sees the server, the API key, or the filesystem.
It returns Python code, which is executed ONLY inside the sandbox.
"""
import os
import re

import httpx

BASE_URL = os.getenv("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1")
API_KEY = os.getenv("VULTR_INFERENCE_API_KEY", "")
MODEL = os.getenv("VULTR_MODEL", "")

SYSTEM_PROMPT = """You write Python pandas code to answer a question about a CSV file.

Rules:
- The CSV is at /data/input.csv . Load it with: df = pd.read_csv('/data/input.csv')
- pandas is imported as pd, matplotlib.pyplot as plt. Do not import anything else
  except math. No os, sys, subprocess, socket, open() on any other path.
- Print the answer (numbers / table) to stdout with print().
- If a chart helps, save ONE chart to /out/chart.png with plt.savefig('/out/chart.png').
- If the result is a table, also save it to /out/result.csv with .to_csv('/out/result.csv', index=False).
- Output ONLY Python code. No markdown fences, no explanations.
"""


def _clean(code: str) -> str:
    code = code.strip()
    code = re.sub(r"^```(python)?", "", code).strip()
    code = re.sub(r"```$", "", code).strip()
    return code


async def generate_code(question: str, columns: list[str], sample: str,
                        previous_error: str | None = None) -> tuple[str, str]:
    """Returns (code, source) where source is 'vultr' or 'fallback'."""
    if API_KEY and MODEL:
        user = f"Columns: {columns}\nSample rows:\n{sample}\n\nQuestion: {question}"
        if previous_error:
            user += f"\n\nThe previous code failed with this error. Fix it:\n{previous_error}"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1,
                },
            )
            r.raise_for_status()
            code = r.json()["choices"][0]["message"]["content"]
        return _clean(code), "vultr"

    return fallback_code(question, columns), "fallback"


def fallback_code(question: str, columns: list[str]) -> str:
    """Offline generator for local testing without an inference key.

    Handles the common demo patterns: total / average / highest-by-category.
    Real answers in production come from Vultr Serverless Inference.
    """
    q = question.lower()
    return f'''import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv('/data/input.csv')
numeric = df.select_dtypes(include="number").columns.tolist()
categorical = [c for c in df.columns if c not in numeric]
print("Rows:", len(df))
print("Columns:", list(df.columns))

question = {q!r}
if categorical and numeric:
    cat, num = categorical[0], numeric[0]
    grouped_sum = df.groupby(cat)[num].sum().sort_values(ascending=False)
    grouped_mean = df.groupby(cat)[num].mean().sort_values(ascending=False)
    if "average" in question or "mean" in question:
        result = grouped_mean
        print(f"Average of {{num}} by {{cat}}:")
    else:
        result = grouped_sum
        print(f"Total of {{num}} by {{cat}} (highest first):")
    print(result.to_string())
    result.to_csv('/out/result.csv', header=["value"])
    plt.figure(figsize=(8, 4.5))
    result.head(10).plot(kind="bar")
    plt.title(f"{{num}} by {{cat}}")
    plt.tight_layout()
    plt.savefig('/out/chart.png')
elif numeric:
    print(df[numeric].describe().to_string())
else:
    print(df.head(10).to_string())
'''
