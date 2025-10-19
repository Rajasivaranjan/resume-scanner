#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, zipfile, importlib
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

# Ensure local imports work regardless of how Streamlit is launched
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------- Helpers ----------------------------
def df_from_ranked(ranked: List[dict]) -> pd.DataFrame:
    rows = []
    for i, r in enumerate(ranked, start=1):
        res = r["result"]
        rows.append({
            "rank": i,
            "pdf_file": r["pdf_path"].name,
            "name": res.get("name", ""),
            "email": res.get("email", ""),
            "phone": res.get("phone", ""),
            "score": res.get("score", 0),
            "verdict": res.get("verdict", ""),
            "strengths": "; ".join(res.get("strengths", []) or []),
            "gaps": "; ".join(res.get("gaps", []) or []),
            "reasoning": res.get("reasoning", ""),
        })
    return pd.DataFrame(rows)

def list_pdfs_in_folder(folder: Path, recursive: bool = False) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(folder.glob(pattern))

def read_zip_member(zp: Path, member: str):
    if not zp or not Path(zp).exists():
        return None
    with zipfile.ZipFile(zp, "r") as zf:
        if member in zf.namelist():
            return zf.read(member)
    return None

# ---------------------------- UI ----------------------------
st.set_page_config(page_title="Resume Screening (Gemini)", page_icon="📄", layout="wide")
st.title("📄 Resume Screening – Gemini")

with st.sidebar:
    st.header("Configuration")
    default_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")
    api_key = st.text_input(
        "Gemini API Key",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="Set via environment variable GEMINI_API_KEY or paste here.",
    )
    model_name = st.text_input("Model name", value=default_model, help="e.g., gemini-2.5-pro")
    top_k = st.number_input("Top K", min_value=1, max_value=50, value=int(os.getenv("TOP_K", "10")))
    verbose = st.toggle("Show verbose logs", value=True)
    st.caption("Tip: turn on recursive to include PDFs in subfolders.")

# ---------- JD input ----------
st.subheader("Job Description")
jd_mode = st.radio("Provide JD as:", ["Paste text", "Upload .txt"], horizontal=True)
jd_text = ""
if jd_mode == "Paste text":
    jd_text = st.text_area("Paste JD text", height=180, placeholder="Paste the job description…")
else:
    jd_file = st.file_uploader("Upload JD (.txt)", type=["txt"], accept_multiple_files=False)
    if jd_file:
        jd_text = jd_file.read().decode("utf-8", errors="ignore")

# ---------- Folder picker for PDFs ----------
st.subheader("Resumes folder")
cols = st.columns([3, 1, 1])
with cols[0]:
    default_folder = os.getenv("DEFAULT_PDF_DIR", "")
    folder_str = st.text_input(
        "Absolute folder path containing PDF resumes",
        value=default_folder,
        placeholder="/Users/you/Documents/resumes",
        help="Enter a local path on the machine running Streamlit."
    )
with cols[1]:
    recursive = st.checkbox("Recursive", value=False, help="Include PDFs in all subfolders.")
with cols[2]:
    refresh = st.button("🔍 Scan folder", use_container_width=True)

pdf_paths: List[Path] = []
folder_path = Path(folder_str).expanduser()

if folder_str:
    if refresh or True:
        pdf_paths = list_pdfs_in_folder(folder_path, recursive=recursive)
        if pdf_paths:
            st.success(f"Found {len(pdf_paths)} PDF(s) in `{folder_path}`" + (" (recursive)" if recursive else ""))
            to_show = [p.name for p in pdf_paths[:15]]
            if len(pdf_paths) > 15:
                to_show.append(f"... and {len(pdf_paths) - 15} more")
            st.write(to_show)
        else:
            if folder_path.exists():
                st.warning(f"No PDFs found in `{folder_path}` (recursive={recursive}).")
            else:
                st.error(f"Folder not found: `{folder_path}`")

# ---------- Run ----------
st.divider()
run_btn = st.button("▶️ Run Screening", type="primary", use_container_width=True)

# ---------------------------- Action ----------------------------
if run_btn:
    if not api_key:
        st.error("Please provide a Gemini API key.")
        st.stop()
    if not jd_text or not jd_text.strip():
        st.error("Please provide the Job Description (paste or upload a .txt file).")
        st.stop()
    if not pdf_paths:
        st.error("Please provide a valid folder path that contains at least one PDF.")
        st.stop()

    with st.status("Loading scorer…", expanded=True) as status:
        try:
            scorer = importlib.import_module("scorer")
            run_pipeline = getattr(scorer, "run_pipeline")
        except Exception as e:
            status.update(label="Failed to load scorer", state="error")
            st.error("Failed to import `scorer.run_pipeline`. See details below:")
            st.exception(e)
            st.stop()
        status.update(label="Scorer loaded", state="complete")

    # Live log console in UI
    log_container = st.container()
    log_area = log_container.empty()
    log_lines: List[str] = []

    def ui_log(msg: str):
        if not verbose:
            return
        log_lines.append(msg)
        if len(log_lines) > 300:
            del log_lines[: len(log_lines) - 300]
        log_area.code("\n".join(log_lines), language="log")

    with st.status("Scoring resumes…", expanded=True) as status:
        progress = st.progress(0)
        step_text = st.empty()

        def on_progress(i, total, pdf_path, result):
            pct = int(i / total * 100)
            progress.progress(pct)
            line = f"Scored {i}/{total}: {pdf_path.name} → {result.get('score', 0)} ({result.get('verdict','')})"
            step_text.write(line)
            ui_log(line)

        try:
            st.write(f"- Resumes to score: **{len(pdf_paths)}**")
            st.write(f"- Folder: `{folder_path}` (recursive={recursive})")

            st.write("- Running pipeline…")
            # zip_path, ranked = run_pipeline(
            #     pdf_paths=pdf_paths,
            #     jd_text=jd_text.strip(),
            #     model_name=model_name.strip(),
            #     top_k=int(top_k),
            #     api_key=api_key.strip(),
            #     progress_fn=on_progress,
            #     log_fn=ui_log,   # <-- now supported by scorer.run_pipeline
            # )

            zip_path, ranked = run_pipeline(
                pdf_paths=pdf_paths,
                jd_text=jd_text.strip(),
                model_name=model_name.strip(),
                top_k=int(top_k),
                api_key=api_key.strip(),
                progress_fn=on_progress,
            )

            st.write("- Preparing results…")
            df = df_from_ranked(ranked)
            status.update(label="Done!", state="complete")
            st.toast("Screening complete ✅", icon="✅")

            st.success(f"Completed. Ranked {len(ranked)} resume(s).")
            st.dataframe(df, use_container_width=True)

            st.code(f"Artifacts folder: {zip_path.parent}\nZIP: {zip_path}", language="bash")

            with open(zip_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download all artifacts (ZIP)",
                    data=f.read(),
                    file_name="resume_screen_outputs.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

            summary_bytes = read_zip_member(zip_path, "output/summary.csv")
            report_bytes  = read_zip_member(zip_path, "output/report.md")
            full_json_bytes = read_zip_member(zip_path, "output/full_results.json")

            c1, c2, c3 = st.columns(3)
            if summary_bytes:
                with c1:
                    st.download_button("summary.csv", data=summary_bytes, file_name="summary.csv", mime="text/csv", use_container_width=True)
            if report_bytes:
                with c2:
                    st.download_button("report.md", data=report_bytes, file_name="report.md", mime="text/markdown", use_container_width=True)
            if full_json_bytes:
                with c3:
                    st.download_button("full_results.json", data=full_json_bytes, file_name="full_results.json", mime="application/json", use_container_width=True)

        except Exception as e:
            st.exception(e)
