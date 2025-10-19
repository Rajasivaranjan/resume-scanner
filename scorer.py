#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os, re, json, time, tempfile, zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

import fitz  # PyMuPDF
import pandas as pd
import google.generativeai as genai

# ============================== CONFIG ===============================
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")

# PDF extraction / chunking
MAX_TEXT_CHARS   = 120_000
USE_CHUNKING     = True
CHUNK_SIZE       = 60_000
CHUNK_OVERLAP    = 5_000

# Generation settings
TEMPERATURE      = 0.2
TOP_P            = 0.8
TOP_K_SAMPLING   = 40

# Debug
DEBUG_SAVE_RAW   = True  # save raw model outputs into output/raw/

# Optional persistent output directory:
# export RESUME_SCREEN_OUT="/absolute/path/to/save/results"
PERSIST_ROOT_ENV = "RESUME_SCREEN_OUT"

JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "score": {"type": "integer"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["Strong Fit","Good Fit","Borderline","Not a Fit","Error"]},
        "reasoning": {"type": "string"},
    },
    "required": ["name","email","phone","score","strengths","gaps","verdict","reasoning"],
}

PROMPT_TEMPLATE = """You are an expert technical recruiter. Evaluate the CANDIDATE_RESUME against the JOB_DESCRIPTION and return a single JSON object (fitting the provided schema).

JOB_DESCRIPTION:
\"\"\"{job_desc}\"\"\"

CANDIDATE_RESUME (raw extracted text from PDF):
\"\"\"{resume_text}\"\"\"

Scoring rubric (0–100):
- Skills match (40): overlap with must-have tech/tools/skills.
- Relevant experience (30): years, domain fit, responsibilities aligned to JD.
- Impact & outcomes (15): quantifiable results, ownership.
- Communication & clarity (10): well-structured, concise profile.
- Bonus fit (5): preferred qualifications (e.g., location, domain).

Output only the JSON object fitting the provided schema.
"""

# ============================== UTILS =================================
def extract_text_from_pdf(pdf_path: Path) -> str:
    parts: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for i in range(doc.page_count):
            parts.append(doc.load_page(i).get_text())
    text = "\n".join(parts)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return text.strip()

def _chunk_text(txt: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    if not USE_CHUNKING or len(txt) <= chunk_size:
        return [txt]
    out, i, n = [], 0, len(txt)
    while i < n:
        j = min(i + chunk_size, n)
        out.append(txt[i:j])
        i = max(0, j - overlap)
    return out

def _resp_text(resp) -> str:
    # Defensive extraction across SDK versions
    try:
        pf = getattr(resp, "prompt_feedback", None)
        if pf and getattr(pf, "block_reason", None):
            return json.dumps({
                "name":"","email":"","phone":"","score":0,
                "strengths":[],"gaps":[],"verdict":"Error",
                "reasoning":f"Blocked by safety filter: {pf.block_reason}",
            })
    except Exception:
        pass
    try:
        if getattr(resp, "text", None):
            return resp.text
    except Exception:
        pass
    try:
        parts = []
        cand = resp.candidates[0]
        for part in getattr(cand.content, "parts", []) or []:
            t = getattr(part, "text", None)
            if t: parts.append(t)
            elif hasattr(part, "as_dict"):
                d = part.as_dict()
                if d.get("text"): parts.append(d["text"])
        return "".join(parts)
    except Exception:
        return ""

def _safe_json_parse(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    s = raw.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        start, end = s.index("{"), s.rindex("}") + 1
        inner = s[start:end]
        try:
            return json.loads(inner)
        except Exception:
            inner = re.sub(r",\s*([}\]])", r"\1", inner)
            return json.loads(inner)
    except Exception:
        return None

# ========================== MODEL & SCORING ===========================
def build_model(api_key: str, model_name: str):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K_SAMPLING,
            "response_mime_type": "application/json",
            "response_schema": JSON_SCHEMA,
        },
    )

def score_one_text(model, resume_text: str, job_desc: str, raw_sink: Optional[Path] = None) -> Dict[str, Any]:
    prompt = PROMPT_TEMPLATE.format(job_desc=job_desc, resume_text=resume_text)
    last_err = None
    for attempt in range(3):
        try:
            resp = model.generate_content(prompt)
            raw = _resp_text(resp) or ""
            if raw_sink:
                mode = "a" if raw_sink.exists() else "w"
                with open(raw_sink, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\n\n--- RETRY ---\n")
                    f.write(raw)
            try:
                data = json.loads(raw)
            except Exception:
                data = _safe_json_parse(raw)
            if not data:
                raise ValueError("Model did not return valid JSON.")
            # normalize
            data.setdefault("name",""); data.setdefault("email",""); data.setdefault("phone","")
            data.setdefault("score",0); data.setdefault("strengths",[]); data.setdefault("gaps",[])
            data.setdefault("verdict",""); data.setdefault("reasoning","")
            try:
                data["score"] = int(round(float(data["score"])))
            except Exception:
                data["score"] = 0
            return data
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    return {
        "name":"", "email":"", "phone":"", "score":0,
        "strengths":[], "gaps":[], "verdict":"Error",
        "reasoning":f"Scoring failed: {last_err}",
    }

def score_resume(model, resume_text: str, job_desc: str, raw_sink: Optional[Path]) -> Dict[str, Any]:
    chunks = _chunk_text(resume_text)
    best = None
    for idx, ch in enumerate(chunks, start=1):
        sink = raw_sink.with_name(raw_sink.stem + f".part{idx}.txt") if (raw_sink and DEBUG_SAVE_RAW) else None
        res = score_one_text(model, ch, job_desc, raw_sink=sink)
        if (best is None) or (res.get("score", 0) > best.get("score", 0)):
            best = res
    return best or {
        "name":"", "email":"", "phone":"", "score":0,
        "strengths":[], "gaps":[], "verdict":"Error",
        "reasoning":"No chunks produced a valid score.",
    }

# ============================ ARTIFACTS =============================
def _save_artifacts(rows: List[Dict[str, Any]], outdir: Path, top_k: int):
    outdir.mkdir(parents=True, exist_ok=True)

    if not rows:
        pd.DataFrame(columns=["rank","pdf_file","name","email","phone","score","verdict","strengths","gaps","reasoning"])\
          .to_csv(outdir / "summary.csv", index=False)
        (outdir / "report.md").write_text("# Resume Screening Report\n\n_No resumes scored._\n", encoding="utf-8")
        return

    df = pd.DataFrame([
        {
            "rank": i + 1,
            "pdf_file": r["pdf_path"].name,
            "name": r["result"].get("name",""),
            "email": r["result"].get("email",""),
            "phone": r["result"].get("phone",""),
            "score": r["result"].get("score",0),
            "verdict": r["result"].get("verdict",""),
            "strengths": "; ".join(r["result"].get("strengths",[]) or []),
            "gaps": "; ".join(r["result"].get("gaps",[]) or []),
            "reasoning": r["result"].get("reasoning",""),
        }
        for i, r in enumerate(rows)
    ]).sort_values(["rank"])
    df.to_csv(outdir / "summary.csv", index=False)

    lines = ["# Resume Screening Report\n"]
    for i, r in enumerate(rows[:top_k], start=1):
        res = r["result"]
        lines.append(f"## {i}. {res.get('name') or r['pdf_path'].name}")
        lines.append(f"- **File**: `{r['pdf_path'].name}`")
        lines.append(f"- **Score**: {res.get('score',0)}")
        lines.append(f"- **Verdict**: {res.get('verdict','')}")
        contact = ", ".join([x for x in [res.get("email"), res.get("phone")] if x])
        if contact: lines.append(f"- **Contact**: {contact}")
        strengths = res.get("strengths") or []
        gaps = res.get("gaps") or []
        if strengths:
            lines.append("- **Strengths:**"); lines += [f"  - {s}" for s in strengths]
        if gaps:
            lines.append("- **Gaps:**"); lines += [f"  - {g}" for g in gaps]
        if res.get("reasoning"):
            lines.append(f"- **Reasoning:** {res['reasoning']}")
        lines.append("")
    (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")

# ============================ PIPELINE =============================
def _prepare_root_dir() -> Path:
    env_root = os.getenv(PERSIST_ROOT_ENV)
    if env_root:
        root = Path(env_root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()
    return Path(tempfile.mkdtemp(prefix="resume_screen_"))

def run_pipeline(
    pdf_paths: List[Path],
    jd_text: str,
    model_name: str,
    top_k: int,
    api_key: str,
    progress_fn: Optional[Callable[[int,int,Path,Dict[str,Any]], None]] = None,
) -> Tuple[Path, List[Dict[str, Any]]]:
    root = _prepare_root_dir()
    output_dir = root / "output"
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    model = build_model(api_key=api_key, model_name=model_name)

    results: List[Dict[str, Any]] = []
    total = len(pdf_paths)

    for idx, pdf_path in enumerate(pdf_paths, start=1):
        try:
            text = extract_text_from_pdf(pdf_path)
            if not text:
                raise ValueError("Empty text extracted (maybe scanned without OCR).")
            raw_sink = (raw_dir / (pdf_path.stem + ".txt")) if DEBUG_SAVE_RAW else None
            scored = score_resume(model, text, jd_text, raw_sink=raw_sink)
            results.append({"pdf_path": pdf_path, "result": scored})
        except Exception as e:
            results.append({
                "pdf_path": pdf_path,
                "result": {
                    "name":"", "email":"", "phone":"", "score":0,
                    "strengths":[], "gaps":[], "verdict":"Error",
                    "reasoning":f"Pipeline failed: {e}",
                },
            })

        if callable(progress_fn):
            try:
                progress_fn(idx, total, pdf_path, results[-1]["result"])
            except Exception:
                pass

    ranked = sorted(results, key=lambda r: r["result"].get("score", 0), reverse=True)

    _save_artifacts(ranked, output_dir, top_k)

    full_json = [
        {"pdf_file": r["pdf_path"].name, "absolute_path": str(r["pdf_path"].resolve()), **r["result"]}
        for r in ranked
    ]
    (output_dir / "full_results.json").write_text(
        json.dumps(full_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    zip_path = root / "resume_screen_outputs.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in output_dir.rglob("*"):
            zf.write(p, p.relative_to(root).as_posix())

    return zip_path, ranked
