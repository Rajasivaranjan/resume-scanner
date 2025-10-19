# resume-scanner
Resume Scanner: Streamlit + Gemini app to screen a folder of PDF resumes against a Job Description. Extracts text, scores candidates (0–100) based on skills, experience, impact, clarity, and bonus fit, then ranks them. Exports summary.csv, report.md, full_results.json, plus a one-click ZIP download.


# Resume Scanner

Screen a **folder of PDF resumes** against a **Job Description** using **Streamlit + Google Gemini**.
The app extracts text from PDFs, scores each candidate on a transparent rubric, and returns a **ranked shortlist** with **downloadable artifacts** (CSV, Markdown report, JSON, ZIP).

> **Why?** First-pass resume review shouldn’t take hours—or be a black box. Resume Scanner is fast, auditable, and easy to run locally.

---

## ✨ Features

* **Folder-based input**: Point to a local folder; optional **recursive** scan (`**/*.pdf`).
* **Flexible JD input**: Paste text or upload a `.txt` file.
* **AI Scoring (0–100)** with a strict JSON schema (valid, structured outputs).
* **Clear verdicts**: *Strong Fit, Good Fit, Borderline, Not a Fit* with strengths/gaps.
* **Artifacts**:

  * `summary.csv` (sortable table of all candidates)
  * `report.md` (Top-K highlights)
  * `full_results.json` (complete data)
  * One-click **ZIP** of everything
* **Progress UI**: Shows `filename → score (verdict)` as it runs.
* **Optional persistent output** via environment variable.

---

## 🧪 Scoring Rubric (0–100)

* **Skills match (40)** – overlap with must-have tech/tools/skills in the JD
* **Relevant experience (30)** – years, responsibilities, domain fit
* **Impact & outcomes (15)** – quantified results, ownership, scope
* **Communication & clarity (10)** – well-structured, concise profile
* **Bonus fit (5)** – preferred extras (e.g., domain, location, certs)

Long resumes are chunked and scored per chunk; the **best chunk wins** to avoid token limits.

---

## 🖼️ UI Snapshot

```
📄 Resume Scanner
[ JD: paste/upload ]  [ Folder: /path/to/resumes ]  [Recursive]
▶ Run Screening  →  filename.pdf → 78 (Good Fit)
Results table + Download: ZIP / CSV / MD / JSON
```

---

## 🚀 Quickstart

### 1) Create an environment

**Python venv (Windows/macOS/Linux):**

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

**Or Conda:**

```bash
conda create -n resume-scanner python=3.12 -y
conda activate resume-scanner
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Set your Gemini API key

```bash
# macOS/Linux
export GEMINI_API_KEY="YOUR_API_KEY"

# Windows (PowerShell)
$env:GEMINI_API_KEY="YOUR_API_KEY"
```

### 4) Run the app

```bash
python -m streamlit run app.py
```

Open the local URL shown in your terminal.

---

## 📁 Using the App

1. **Job Description**: Paste text or upload a `.txt` JD.
2. **Resumes Folder**: Enter an absolute path to a folder containing `*.pdf` resumes.

   * Toggle **Recursive** to include subfolders.
3. **Run**: Click **▶ Run Screening**.
4. **Results**: View a ranked table and **download**: ZIP, `summary.csv`, `report.md`, `full_results.json`.

> Tip: set a default folder path with `DEFAULT_PDF_DIR` (env var) to pre-fill the input.

---

## 📦 Outputs

* `output/summary.csv` — rank, file, score, verdict, contact fields, strengths/gaps
* `output/report.md` — Top-K readable summary
* `output/full_results.json` — all model fields for each candidate
* `resume_screen_outputs.zip` — zipped `output/` directory

To persist outputs to a fixed location:

```bash
# macOS/Linux
export RESUME_SCREEN_OUT="$HOME/Documents/resume-scanner-results"
# Windows (PowerShell)
$env:RESUME_SCREEN_OUT="C:\Users\you\Documents\resume-scanner-results"
```

---

## 🧱 Project Structure

```
resume-scanner/
├─ app.py           # Streamlit UI (folder input, JD input, results)
├─ scorer.py        # Pure Python scoring pipeline (no Streamlit imports)
├─ requirements.txt
└─ pdf/             # (optional) sample resumes
```

---

## ⚙️ Configuration (env vars)

* `GEMINI_API_KEY` — **required**
* `DEFAULT_MODEL` — default `gemini-2.5-pro`
* `TOP_K` — top-K for `report.md` (default 10)
* `DEFAULT_PDF_DIR` — prefill the folder path input
* `RESUME_SCREEN_OUT` — persist outputs to a chosen directory

---

## 🔐 Privacy

* All processing happens locally on your machine.
* PDFs are parsed with **PyMuPDF**; extracted text + model outputs are written to your local `output/` folder (or `RESUME_SCREEN_OUT`).
* Remove `output/` after review if needed.

---

## ❓ FAQ

**Q: Some PDFs return empty text.**
A: They’re likely scanned images without text (no OCR). Run OCR first (e.g., Adobe, Tesseract, or macOS Preview “Recognize Text”) and re-try.

**Q: The app can’t find my folder.**
A: Use an **absolute** path and ensure your user has read permissions. On macOS Sonoma+, you may need to grant Terminal/IDE “Full Disk Access” if reading protected directories.

**Q: Model errors or weird JSON?**
A: The pipeline retries and uses a strict schema + robust JSON repair. Errors are still shown, but won’t crash the run.

---


## 📝 License

MIT — use freely in personal or commercial projects. Contributions welcome!

---

## 🙌 Credits

Built with **Streamlit**, **PyMuPDF**, **pandas**, and **Google Gemini**.


