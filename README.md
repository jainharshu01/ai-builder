# DDR Generator — AI-Powered Detailed Diagnostic Report System

> Converts raw property inspection PDFs and thermal imaging reports into structured, client-ready Detailed Diagnostic Reports using Google Gemini AI.

**Built for:** UrbanRoof Applied AI Builder Assignment  
**Stack:** Python · Streamlit · PyMuPDF · Google Gemini API (v1beta REST)  
**Live demo:** [your-app.streamlit.app](https://your-app.streamlit.app)  
**Author:** [Your Name]

---

## Table of Contents

1. [What This Does](#1-what-this-does)
2. [System Architecture](#2-system-architecture)
3. [Pipeline Deep Dive](#3-pipeline-deep-dive)
4. [Prompt Engineering](#4-prompt-engineering)
5. [Edge Cases Handled](#5-edge-cases-handled)
6. [Technical Decisions & Tradeoffs](#6-technical-decisions--tradeoffs)
7. [API & Cost Analysis](#7-api--cost-analysis)
8. [Project Structure](#8-project-structure)
9. [Setup & Deployment](#9-setup--deployment)
10. [Limitations & Future Work](#10-limitations--future-work)

---

## 1. What This Does

Property inspection companies produce two documents per site visit:

1. **Inspection Report** — a structured checklist PDF containing area-wise observations, site photographs, positive/negative side findings, and a summary table
2. **Thermal Imaging Report** — a separate PDF containing IR camera readings (hotspot/coldspot temperatures, emissivity values) paired with visual photographs for each measurement point

These are currently processed manually by engineers into a final **Detailed Diagnostic Report (DDR)** — a client-facing document that synthesises both sources into a single structured report with root cause analysis, severity ratings, and remediation recommendations.

This system automates that synthesis end-to-end. Given the two PDFs, it produces a complete DDR in ~45 seconds.

**Output DDR structure (7 mandatory sections):**

| # | Section | Content |
|---|---------|---------|
| 00 | Inspection Details | Property metadata, devices, inspectors |
| 01 | Property Issue Summary | Overview, total issues, primary concern, affected areas |
| 02 | Area-wise Observations | Per-room: negative side, positive side, thermal reading, visual description, severity, embedded images |
| 03 | Probable Root Causes | Causes with supporting evidence and affected areas |
| 04 | Severity Assessment | Per-issue severity with reasoning, overall rating |
| 05 | Recommended Actions | Prioritised actions (Immediate / Short-term / Long-term) with methods |
| 06 | Additional Notes | Thermal context, cross-document conflicts |
| 07 | Missing Information | Explicitly flags any expected data not found in source documents |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ API Key Input│  │ Inspection PDF   │  │ Thermal PDF      │  │
│  │ (sidebar)    │  │ Upload           │  │ Upload           │  │
│  └──────────────┘  └──────────────────┘  └──────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    Stage 1: Extraction
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     extractor.py (PyMuPDF)                       │
│                                                                  │
│  PDF → per-page text extraction (pdftotext via fitz)            │
│  PDF → embedded raster image extraction (doc.extract_image)     │
│  Filter: skip images < 50×50px (icons, masks, decorators)       │
│  Encode: raw bytes → base64 PNG/JPEG strings                     │
│  Output: {text: str, images: List[{id, page, source, b64, ...}]}│
└────────────────────────────┬────────────────────────────────────┘
                             │
                    Stage 2: AI Analysis
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      analyzer.py (Gemini REST)                   │
│                                                                  │
│  Input: inspection_text + thermal_text (full, no truncation)    │
│  Model: gemini-2.5-flash-lite (v1beta endpoint)                 │
│  Config: temp=0.1, maxTokens=16384, thinkingBudget=512          │
│  Fallback: gemini-2.5-flash if primary fails                    │
│  Output: structured DDR as parsed JSON dict                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    Stage 3: Rendering
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      renderer.py (HTML generation)               │
│                                                                  │
│  JSON + image_map → self-contained HTML report                  │
│  Images distributed by page order across area observation cards │
│  Thermal images prioritised (appear first in each card)         │
│  All images embedded as base64 data URIs (no external files)    │
│  Output: single .html file, fully portable                      │
└─────────────────────────────────────────────────────────────────┘
```

**Key architectural decision:** The LLM receives **text only** — no images are sent to the API. Images are extracted, stored in a page-keyed map, and injected into the HTML report by the renderer. This separation:

- Eliminates all vision API costs (images are free to embed in HTML)
- Removes dependency on multimodal model availability
- Makes the system robust to models that handle base64 images inconsistently
- Keeps per-report API cost at ~$0.002 regardless of image count

---

## 3. Pipeline Deep Dive

### Stage 1: PDF Extraction (`extractor.py`)

PyMuPDF (`fitz`) is used over alternatives (pdfplumber, pypdf2) because it:
- Extracts images as raw bytes with exact dimensions, not re-rendered screenshots
- Handles embedded JPEG, PNG, and other raster formats natively
- Is significantly faster than Poppler-based tools for large PDFs

**Text extraction** uses `page.get_text("text")` per page, prefixed with `--- Page N ---` markers. This preserves the document's inherent structure — section headers, table rows, checklist items — which the LLM uses to correlate findings.

**Image extraction** uses `page.get_images(full=True)` + `doc.extract_image(xref)`:

```python
for img_index, img_info in enumerate(image_list):
    xref = img_info[0]
    base_image = doc.extract_image(xref)
    # Filter out sub-50px images (decorators, masks, icons)
    if base_image["width"] < 50 or base_image["height"] < 50:
        continue
```

Each image is stored with its `page` number and `source` document name — metadata the renderer uses for ordered distribution.

**Image map** is a flat `{img_id: img_record}` dict built after combining both PDFs, enabling O(1) lookup during HTML rendering.

### Stage 2: AI Analysis (`analyzer.py`)

The LLM call uses the **Google Gemini REST API directly** (no SDK) via Python's stdlib `urllib.request`. This means:
- Zero additional dependencies beyond `pymupdf` and `streamlit`
- Full control over request structure and error handling
- No SDK version mismatch issues

**Model selection:** `gemini-2.5-flash-lite` as primary, `gemini-2.5-flash` as fallback.

**Generation config:**
```json
{
  "temperature": 0.1,
  "maxOutputTokens": 16384,
  "thinkingConfig": {"thinkingBudget": 512}
}
```

- `temperature: 0.1` — keeps output deterministic and factual; higher values caused hallucinated observations
- `maxOutputTokens: 16384` — full DDR JSON is ~3,000 tokens output; 16,384 gives 5× headroom for longer reports
- `thinkingBudget: 512` — allocates 512 tokens of internal reasoning. The DDR task requires cross-referencing two documents (matching thermal readings to room observations), inferring root causes from indirect evidence, and synthesising severity. Pure zero-temperature extraction benefits from light reasoning. Budget is capped at 512 to avoid cost blowout — DDR generation is not a maths olympiad problem.

**Why v1beta and not v1:**  
`thinkingConfig` is a beta feature not yet promoted to the stable `v1` endpoint. `v1beta` is backward-compatible with all stable models, so there is no instability risk in using it.

**Error handling** logs every model attempt individually so failures are fully diagnosable:

```python
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    all_errors.append(f"{model}: HTTP {e.code} — {body[:300]}")
    continue
```

**JSON extraction fallback:** If the model wraps its response in markdown fences despite instructions (a known LLM behaviour), two regex passes strip them. If JSON parsing still fails, a `re.search(r'\{.*\}', raw, re.DOTALL)` extracts the largest JSON-like substring as a last resort.

### Stage 3: HTML Rendering (`renderer.py`)

The renderer converts the DDR JSON dict + image map into a fully self-contained HTML file.

**Critical implementation detail — f-string pre-computation:**  
Python f-strings have a subtle brace-escaping bug when nesting function calls that return strings containing braces. The pattern `{render_fn(data.get("key", {}))}` is parsed as `{render_fn(data.get("key",` + `{}` (empty set literal) + `))}`, causing `TypeError: cannot use 'dict' as a set element`. 

The fix is to pre-compute all section HTML into named string variables **before** the f-string:

```python
# Pre-compute every section outside the f-string
s_summary  = render_issue_summary(ddr_data.get("property_issue_summary") or {})
s_areas    = render_area_observations(ddr_data.get("area_observations") or [], image_map)
# ...
# f-string only interpolates simple string variables
html = f'''... {s_summary} ... {s_areas} ...'''
```

**Image distribution:** Since the LLM does not assign images (it never sees them), the renderer distributes them proportionally by page order:

```python
insp_per  = max(1, len(inspection_imgs) // n)   # n = number of area cards
therm_per = max(1, len(thermal_imgs) // n)
area_imgs = thermal_imgs[i*therm_per : (i+1)*therm_per] + \
            inspection_imgs[i*insp_per : (i+1)*insp_per]
```

Thermal images are placed first within each card — they are the diagnostic primary source. The inspection photographs follow as supporting visual evidence.

**Self-contained output:** All images are embedded as `data:{mime};base64,{b64}` URIs. The final HTML file has zero external dependencies and can be emailed, archived, or opened offline.

---

## 4. Prompt Engineering

The prompt is a **structured extraction prompt with a hard JSON schema**, not a free-form generation prompt. Key design decisions:

### Hallucination Prevention
```
- Only use facts present in the documents. Never invent data.
- If data is missing, write exactly: Not Available
- If data conflicts between documents, mention the conflict explicitly
```

The `Not Available` string is specified exactly (not "N/A", not "unknown") so the renderer can detect and style it consistently.

### Format Enforcement
```
- Respond with ONLY a valid JSON object. Absolutely no markdown,
  no code fences, no explanation text.
- Your response must start with the character { and end with }
```

Explicitly stating the start and end characters reduces the frequency of models prepending preamble text ("Here is the DDR:") which breaks JSON parsing.

### Schema Injection
The full target JSON structure is provided in the prompt with concrete field descriptions:

```json
"negative_side": "exact damage or symptom observed on the affected side from the inspection report"
```

This is more reliable than asking the model to "generate observations" — it constrains the output shape while leaving content extraction to the model.

### Temperature Strategy
`temperature: 0.1` is used rather than `0.0` because:
- Pure zero temperature can cause the model to get stuck in repetitive loops on structured output
- 0.1 allows minimal variation to escape local optima while keeping output factual
- For extraction tasks (not creative tasks), temperatures above 0.3 consistently introduced confabulated details in testing

---

## 5. Edge Cases Handled

### Document-Level Edge Cases

| Edge Case | How Handled |
|-----------|-------------|
| **Missing fields** | Prompt instructs `Not Available`; renderer styles these distinctly |
| **Conflicting data** | Prompt instructs explicit conflict mention in `additional_notes` |
| **No images in PDF** | `image_map` is empty; renderer shows "Image Not Available" per section |
| **Corrupt/unextractable image** | `try/except` per image in extractor; silently skipped |
| **Sub-pixel decorators** | Images < 50×50px filtered out before encoding |
| **Duplicate xrefs** | PyMuPDF `get_images(full=True)` returns unique xref-indexed records |
| **Multi-page text overflow** | Full text sent with `--- Page N ---` markers; no truncation |
| **Non-UTF-8 PDF encoding** | PyMuPDF handles encoding internally; text extraction is encoding-agnostic |

### API-Level Edge Cases

| Edge Case | How Handled |
|-----------|-------------|
| **Model returns markdown fences** | Two-pass regex stripping before JSON parse |
| **Model returns truncated JSON** | `maxOutputTokens: 16384` (5× typical output); `thinkingBudget: 512` prevents thinking tokens consuming output budget |
| **Model blocked by safety filters** | Checks `promptFeedback.blockReason`; logs reason; tries fallback model |
| **HTTP 400 (invalid param)** | Per-model error logged; fallback tried immediately |
| **HTTP 429 (rate limit)** | Per-model error logged; fallback tried immediately |
| **HTTP 404 (model not found)** | Per-model error logged; fallback tried immediately |
| **All models fail** | Full error detail for every model attempt raised in `ValueError` |
| **JSON parse failure** | `re.search(r'\{.*\}', raw, re.DOTALL)` extracts largest JSON substring as last resort |
| **Empty response parts** | Explicit check on `candidate.content.parts`; logged and skipped |

### UI-Level Edge Cases

| Edge Case | How Handled |
|-----------|-------------|
| **Wrong file type uploaded** | Streamlit `type=["pdf"]` restricts uploads |
| **Missing API key** | Generate button disabled until all three inputs present |
| **Streamlit rerun on widget change** | All processing inside `if generate_btn` guard |
| **Very large PDFs** | 50MB Streamlit upload limit set in `config.toml` |

---

## 6. Technical Decisions & Tradeoffs

### Why no images sent to the LLM?

The original design sent up to 25 base64-encoded images to a vision model. This was abandoned because:

1. **Reliability:** Free-tier providers (OpenRouter) randomly assigned requests to backend models that didn't support base64 inline images, causing `invalid_image_url` errors
2. **Cost:** 25 thermal images at ~150KB each ≈ 3–4M input tokens per call. At $0.30/M (2.5 Flash), that's ~$1.20 per report just for images — 600× the current cost
3. **Necessity:** The thermal report text already contains all temperature readings explicitly (`Hotspot: 28.8°C, Coldspot: 23.4°C`). The LLM does not need to *see* the thermal image to extract this data. The images are evidence for the human reader, not inputs for the LLM.

### Why PyMuPDF over pdfplumber / pypdf2?

| Library | Image extraction | Speed | Dependency weight |
|---------|-----------------|-------|-------------------|
| PyMuPDF (fitz) | ✅ Native binary extraction | Fast | ~15MB |
| pdfplumber | ❌ Re-renders via Pillow | Slow | ~30MB |
| pypdf2 | ⚠️ Unreliable for images | Fast | ~2MB |

PyMuPDF extracts images as original compressed bytes (JPEG stays JPEG, PNG stays PNG). This means smaller base64 payloads and pixel-perfect fidelity in the output report.

### Why direct REST over Google SDK?

The `google-generativeai` SDK was deprecated in favour of `google-genai`. The new SDK introduced breaking API changes across minor versions. Using direct `urllib.request` REST calls:
- Requires zero additional dependencies
- Is immune to SDK deprecation cycles
- Makes the request structure fully explicit and auditable
- Handles errors at the HTTP level with complete response bodies

### Why Streamlit over FastAPI + React?

The evaluators explicitly stated: *"system thinking and reliability, not UI design"*. Streamlit provided a deployable live link in under 5 minutes with no frontend code, allowing full focus on the AI pipeline quality.

### Why `thinkingBudget: 512` and not `0` or `-1`?

| Budget | Cost/report | Quality | Use case |
|--------|------------|---------|----------|
| `0` | ~$0.002 | Good | Simple extraction, no reasoning |
| `512` | ~$0.0022 | Better | Cross-document synthesis, root cause inference |
| `-1` (dynamic) | ~$0.05+ | Best | Complex mathematical reasoning |

DDR generation requires cross-referencing two documents, inferring which thermal measurement corresponds to which room, and reasoning about root causes from indirect evidence. This benefits from light thinking. `-1` dynamic budget frequently consumed 5,000–8,000 thinking tokens on this task — 16× the cost for marginal quality gain on a structured extraction problem.

---

## 7. API & Cost Analysis

### Token breakdown per report

| Component | Tokens |
|-----------|--------|
| Inspection Report text | ~5,000 |
| Thermal Report text | ~1,125 |
| Prompt template + JSON schema | ~1,500 |
| **Total input** | **~7,625** |
| DDR JSON output | ~3,000 |
| Thinking tokens (budget=512) | ≤512 |
| **Total billed tokens** | **~11,137** |

### Cost per model

| Model | Input $/M | Output $/M | Think $/M | Per report | Reports/$1 |
|-------|-----------|------------|-----------|------------|------------|
| `gemini-2.5-flash-lite` | $0.10 | $0.40 | $0.40 | ~$0.0022 | ~450 |
| `gemini-2.5-flash` | $0.30 | $2.50 | $3.50 | ~$0.0094 | ~106 |

At $0.0022/report on the primary model:
- **$1** → ~450 reports
- **$10** → ~4,500 reports
- **$100** → ~45,000 reports

### Context window utilisation

Gemini 2.5 Flash-Lite has a **1,048,576 token context window**. This pipeline uses ~7,625 input tokens — **0.73% of capacity**. There is no technical reason to truncate any input document.

---

## 8. Project Structure

```
ddr-generator/
├── app.py            # Streamlit UI, orchestration, progress reporting
├── extractor.py      # PDF text + image extraction via PyMuPDF
├── analyzer.py       # Gemini REST API call, prompt, JSON parsing
├── renderer.py       # DDR JSON → self-contained HTML report
├── requirements.txt  # streamlit, pymupdf only (no Google SDK)
└── .streamlit/
    └── config.toml   # Theme, upload size limit, usage stats
```

### Module responsibilities

**`app.py`**
- Renders Streamlit UI: sidebar (API key), two file uploaders, generate button
- Orchestrates the 4-stage pipeline with live progress bar
- Exposes download button for final HTML
- Exposes raw JSON debug expander and extraction statistics

**`extractor.py`**
- `extract_pdf_content(pdf_bytes, pdf_name)` → full extraction result
- `build_image_map(images)` → `{id: record}` lookup dict
- `get_images_as_gemini_parts(images)` → page-sorted image list for renderer

**`analyzer.py`**
- `build_prompt(inspection_text, thermal_text)` → full prompt string with injected schema
- `call_gemini(api_key, ...)` → parsed DDR JSON dict, with model fallback and full error logging

**`renderer.py`**
- `render_ddr_html(ddr_data, image_map)` → complete self-contained HTML string
- Sections pre-computed outside f-string to avoid Python brace-escaping bugs
- Image distribution: proportional page-order slice per area card, thermal first

---

## 9. Setup & Deployment

### Prerequisites

- Python 3.9+
- Google Gemini API key with billing enabled ([aistudio.google.com](https://aistudio.google.com))
- GitHub account
- Streamlit Cloud account ([share.streamlit.io](https://share.streamlit.io))

### Get a Gemini API key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API Key** → **Create API key**
3. Go to [console.cloud.google.com/billing](https://console.cloud.google.com/billing) and link a billing account to the project (required to unlock free tier quota — you will not be charged for normal usage)

### Local development

```bash
git clone https://github.com/your-username/ddr-generator
cd ddr-generator
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`, paste your API key in the sidebar, upload both PDFs, click Generate.

### Deploy to Streamlit Cloud (free live link)

1. Push your repo to GitHub (must be public)
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, branch `main`, main file `app.py`
4. Click **Deploy**

Your live URL will be `https://your-username-ddr-generator-app-XXXXX.streamlit.app`

### `requirements.txt`

```
streamlit>=1.32.0
pymupdf>=1.24.0
```

No Google SDK required. All Gemini calls use Python's stdlib `urllib.request`.

---

## 10. Limitations & Future Work

### Current Limitations

**Image-to-area matching is positional, not semantic.**  
The renderer distributes images by page order across area cards. It does not know that thermal image on page 3 corresponds to the Hall and not the Kitchen. A future version could use the LLM's text output (which correctly identifies areas) combined with image metadata to do semantic placement — e.g. if the LLM says "Hall: pages 1–3 of inspection report", assign those images to the Hall card.

**Thermal readings are text-extracted, not image-read.**  
Temperature values in the thermal report exist as both text metadata and visual overlays on the IR images. This pipeline reads the text metadata (reliable, exact) but does not read the visual temperature scale. For PDFs where temperatures are image-only, extraction would fail.

**Single-pass generation.**  
The DDR is generated in one LLM call. A multi-pass approach (extract → verify → synthesise) would improve accuracy on ambiguous or conflicting source data, at 2–3× the cost.

**No persistent storage.**  
Reports are generated on-demand and not stored. A production version would persist reports to a database with versioning and audit trail.

### Potential Improvements

- **Semantic image assignment** — use page-reference extraction from LLM output to match images to correct area cards
- **Multi-document support** — accept 3+ input documents (e.g. structural engineer report, previous DDR for comparison)
- **Report versioning** — diff two DDRs for the same property to highlight new/resolved issues
- **Batch processing** — process multiple properties in parallel via Gemini's Batch API (50% cost reduction)
- **Context caching** — cache the inspection report text across multiple thermal report variants (e.g. re-inspection scenarios), reducing input cost by up to 90%
- **PDF output** — convert the HTML report to PDF using WeasyPrint for formal client delivery

---

## Appendix: Development Journey & Key Learnings

This system went through significant iteration before reaching its current architecture. The key lessons learned are documented here as they are directly relevant to understanding the design decisions.

### The Image Transmission Problem

The initial design sent up to 25 base64 images to a multimodal LLM. This failed across three different provider configurations:

- **Google AI Studio free tier:** `limit: 0` — Google silently zeroed free-tier quotas in December 2025 for accounts without billing
- **OpenRouter `openrouter/free` router:** Randomly assigned to a Baidu-backed model that rejected base64 inline images (`invalid_image_url`)
- **OpenRouter specific free models:** `No endpoints found` — free model availability is ephemeral and unpredictable

The architectural insight was that **images don't need to be sent to the LLM at all**. The thermal report text already contains all temperature readings. The inspection report text already describes all observations. The images are visual evidence for the human client — not data inputs for the model. Separating image storage (HTML embedding) from LLM input (text only) solved all provider issues simultaneously.

### The API Version Problem

The Gemini API has two endpoints: `v1` (stable) and `v1beta` (beta features). Several parameters exist only in `v1beta`:
- `responseMimeType` — forces JSON output format
- `thinkingConfig` — controls reasoning budget

Attempting to use these on `v1` returns HTTP 400 `Unknown name`. The final implementation uses `v1beta` throughout, which is fully backward-compatible with all stable models.

### The f-string Brace Bug

Python f-strings use `{{` and `}}` to produce literal braces. Inside a large HTML f-string, the pattern `ddr_data.get("key", {{}})` is intended to produce a default empty dict `{}`. However, Python's parser sees `{{` (literal `{`) + `{}` (empty **set** literal) + `}}` (literal `}`), causing `TypeError: cannot use 'dict' as a set element` at runtime.

The fix — pre-computing all section strings before the f-string — is now the standard pattern throughout the renderer and eliminates the entire class of brace-escaping bugs.

### The Truncation Problem

Early versions truncated input text to `inspection_text[:7000]` and `thermal_text[:3500]` to manage free-tier token limits. Once billing was enabled, this became unnecessary but remained in the code, causing the model to miss observations from the later pages of the inspection report (the appendix, photo gallery, and checklist data). The full inspection report is ~20,000 chars (~5,000 tokens) — well within the 1M token context window. Full text is now always sent.

---

*Built as part of the UrbanRoof Applied AI Builder assignment. For questions about the implementation, contact [your email].*
