"""
app.py - Streamlit DDR Generation App
DDR (Detailed Diagnostic Report) generator from inspection + thermal PDFs
"""

import streamlit as st
import json
import time
from pathlib import Path

from extractor import extract_pdf_content, build_image_map
from analyzer import call_gemini
from renderer import render_ddr_html

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="DDR Generator · UrbanRoof",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }
    
    .main-title {
        font-family: 'DM Serif Display', serif;
        font-size: 2.2rem;
        font-weight: 400;
        line-height: 1.2;
        margin-bottom: 0.25rem;
    }
    .main-subtitle {
        color: #666;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .step-label {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: #C8A96E;
        margin-bottom: 4px;
    }
    .info-box {
        background: #FDF5E6;
        border: 1px solid #C8A96E;
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 0.85rem;
        margin-bottom: 16px;
    }
    .stButton > button {
        background: #0D0D0D;
        color: #FAFAF7;
        border: none;
        border-radius: 6px;
        font-family: 'DM Sans', sans-serif;
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0.6rem 2rem;
        transition: all 0.2s;
        width: 100%;
    }
    .stButton > button:hover {
        background: #333;
        color: #C8A96E;
    }
    .success-box {
        background: #F0FFF4;
        border: 1px solid #34C759;
        border-radius: 8px;
        padding: 12px 16px;
        color: #1A6B31;
        font-size: 0.9rem;
    }
    .error-box {
        background: #FFF0EF;
        border: 1px solid #FF3B30;
        border-radius: 8px;
        padding: 12px 16px;
        color: #8B0000;
        font-size: 0.9rem;
    }
    div[data-testid="stFileUploader"] {
        border-radius: 8px;
    }
    .sidebar-brand {
        font-family: 'DM Serif Display', serif;
        font-size: 1.4rem;
        margin-bottom: 4px;
    }
    .sidebar-tagline {
        font-size: 0.75rem;
        color: #888;
        margin-bottom: 24px;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-brand">🏠 UrbanRoof DDR</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-tagline">Detailed Diagnostic Report Generator</div>', unsafe_allow_html=True)
    st.divider()
    
    st.markdown('<div class="step-label">Step 1 · API Key</div>', unsafe_allow_html=True)
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        help="Get a free key at openrouter.ai - no credit card needed",
        label_visibility="collapsed",
    )
    
    if not api_key:
        st.markdown("""
        <div class="info-box">
        🔑 <strong>Get a free key:</strong><br>
        1. Go to <a href="https://openrouter.ai" target="_blank">openrouter.ai</a><br>2. Sign up → Avatar → Keys → Create Key<br>3. Key starts with sk-or-v1- 
        Paste the key into this field
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="success-box">✓ API key entered</div>', unsafe_allow_html=True)
    
    st.divider()
    st.markdown("**About**")
    st.caption("""
    This tool reads two inspection PDFs — a **visual inspection report** and a **thermal imaging report** — 
    and generates a structured Detailed Diagnostic Report (DDR) using Gemini AI.
    
    Images from both documents are extracted and placed in the correct sections of the output report.
    """)
    
    st.divider()
    st.caption("Powered by OpenRouter · Gemini 2.0 Flash (Free) · PyMuPDF · Streamlit")


# ─────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────
st.markdown('<div class="main-title">Detailed Diagnostic Report<br><em>Generator</em></div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Upload two PDFs to generate an AI-powered property health report with embedded thermal images.</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="step-label">Step 2 · Inspection Report PDF</div>', unsafe_allow_html=True)
    inspection_file = st.file_uploader(
        "Inspection Report",
        type=["pdf"],
        key="inspection",
        label_visibility="collapsed",
        help="The visual site inspection report with area observations, photos, and checklist data",
    )
    if inspection_file:
        st.caption(f"✓ {inspection_file.name} ({inspection_file.size // 1024} KB)")

with col2:
    st.markdown('<div class="step-label">Step 3 · Thermal Imaging Report PDF</div>', unsafe_allow_html=True)
    thermal_file = st.file_uploader(
        "Thermal Report",
        type=["pdf"],
        key="thermal",
        label_visibility="collapsed",
        help="The thermal imaging report with temperature readings and infrared images",
    )
    if thermal_file:
        st.caption(f"✓ {thermal_file.name} ({thermal_file.size // 1024} KB)")

st.divider()

# ─────────────────────────────────────────────
# GENERATE BUTTON
# ─────────────────────────────────────────────
st.markdown('<div class="step-label">Step 4 · Generate Report</div>', unsafe_allow_html=True)

ready = bool(api_key and inspection_file and thermal_file)
if not ready:
    missing = []
    if not api_key: missing.append("Gemini API key")
    if not inspection_file: missing.append("Inspection Report PDF")
    if not thermal_file: missing.append("Thermal Report PDF")
    st.caption(f"⚠️ Still needed: {', '.join(missing)}")

generate_btn = st.button("⚡ Generate DDR Report", disabled=not ready, use_container_width=True)

# ─────────────────────────────────────────────
# GENERATION PIPELINE
# ─────────────────────────────────────────────
if generate_btn and ready:
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # ── STEP 1: Extract inspection PDF ──
        status_text.markdown("🔍 **Extracting text and images from Inspection Report...**")
        progress_bar.progress(10)
        
        inspection_bytes = inspection_file.read()
        inspection_data = extract_pdf_content(inspection_bytes, pdf_name="Inspection Report")
        
        st.caption(f"📄 Inspection Report: {inspection_data['total_pages']} pages, {inspection_data['total_images']} images extracted")
        progress_bar.progress(25)
        
        # ── STEP 2: Extract thermal PDF ──
        status_text.markdown("🌡️ **Extracting text and images from Thermal Report...**")
        
        thermal_bytes = thermal_file.read()
        thermal_data = extract_pdf_content(thermal_bytes, pdf_name="Thermal Report")
        
        st.caption(f"🌡️ Thermal Report: {thermal_data['total_pages']} pages, {thermal_data['total_images']} images extracted")
        progress_bar.progress(40)
        
        # ── STEP 3: Build image maps ──
        status_text.markdown("🗂️ **Organising images...**")
        
        all_images_raw = inspection_data["images"] + thermal_data["images"]
        image_map = build_image_map(all_images_raw)
        
        inspection_image_ids = [img["id"] for img in inspection_data["images"]]
        thermal_image_ids = [img["id"] for img in thermal_data["images"]]
        
        # Cap images sent to Gemini to avoid token limits
        # Prioritize thermal images (more diagnostic value) + a subset of inspection images
        from extractor import get_images_as_gemini_parts
        _, selected_inspection_imgs = get_images_as_gemini_parts(inspection_data["images"])
        _, selected_thermal_imgs = get_images_as_gemini_parts(thermal_data["images"])
        
        # Combine: thermal first (higher priority), then inspection
        selected_all = selected_thermal_imgs + selected_inspection_imgs
        # Hard cap at 12 images total to stay within free tier limits
        selected_all = selected_all[:12]
        
        selected_ids = {img["id"] for img in selected_all}
        st.caption(f"🖼️ {len(selected_all)} images selected for AI analysis (thermal: {len(selected_thermal_imgs)}, inspection: {len(selected_inspection_imgs)})")
        
        progress_bar.progress(55)
        
        # ── STEP 4: Call Gemini AI ──
        status_text.markdown("🤖 **Sending to Gemini AI for analysis... (this may take 30–60 seconds)**")
        
        ddr_json = call_gemini(
            api_key=api_key,
            inspection_text=inspection_data["text"],
            thermal_text=thermal_data["text"],
            all_images=selected_all,
            inspection_image_ids=[img["id"] for img in selected_inspection_imgs],
            thermal_image_ids=[img["id"] for img in selected_thermal_imgs],
        )
        
        progress_bar.progress(80)
        status_text.markdown("📝 **Rendering HTML report...**")
        
        # ── STEP 5: Render HTML ──
        html_report = render_ddr_html(ddr_json, image_map)
        
        progress_bar.progress(100)
        status_text.markdown("✅ **Report generated successfully!**")
        time.sleep(0.5)
        
        # ── Display results ──
        st.success("🎉 Your Detailed Diagnostic Report is ready!")
        
        # Download button
        st.download_button(
            label="📥 Download DDR Report (HTML)",
            data=html_report.encode("utf-8"),
            file_name="DDR_Report.html",
            mime="text/html",
            use_container_width=True,
        )
        
        # Preview toggle
        with st.expander("👁️ Preview Report in Browser (embedded)", expanded=False):
            st.components.v1.html(html_report, height=800, scrolling=True)
        
        # Debug: show raw JSON
        with st.expander("🔧 Raw AI Output (JSON)", expanded=False):
            st.json(ddr_json)
        
        # Show image extraction stats
        with st.expander("📊 Extraction Statistics", expanded=False):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Inspection Pages", inspection_data["total_pages"])
                st.metric("Inspection Images", inspection_data["total_images"])
            with col_b:
                st.metric("Thermal Pages", thermal_data["total_pages"])
                st.metric("Thermal Images", thermal_data["total_images"])
            with col_c:
                st.metric("Images Sent to AI", len(selected_all))
                st.metric("Area Observations", len(ddr_json.get("area_observations", [])))
    
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.markdown(f'<div class="error-box">❌ <strong>Error:</strong> {str(e)}</div>', unsafe_allow_html=True)
        
        with st.expander("🔧 Debug Details"):
            st.exception(e)

# ─────────────────────────────────────────────
# FOOTER INFO
# ─────────────────────────────────────────────
st.divider()
with st.expander("ℹ️ How this works"):
    st.markdown("""
    **Pipeline:**
    1. **PDF Extraction** — PyMuPDF extracts all text and embedded images from both PDFs
    2. **Image Selection** — The most content-rich images are selected (up to 25) to stay within API limits  
    3. **AI Analysis** — Gemini 2.0 Flash receives all text + images simultaneously and generates structured DDR data
    4. **Report Rendering** — The structured JSON is converted into a professional HTML report with images embedded directly
    
    **Output format:**
    - Self-contained HTML file (no external dependencies)
    - All images embedded as base64 — can be shared as a single file
    - 7-section DDR structure as per UrbanRoof standards
    
    **Limitations:**
    - Gemini's context window caps at ~1M tokens; very large PDFs may be truncated
    - Image-to-area matching is AI-inferred from visual content — not always 100% accurate
    - The AI is instructed NOT to invent information; missing data appears as "Not Available"
    """)
