"""
renderer.py - Convert DDR JSON into a beautiful, self-contained HTML report
"""

from typing import Dict, List, Any
from datetime import datetime


SEVERITY_COLORS = {
    "High": ("#FF3B30", "#FFF0EF"),
    "Medium": ("#FF9500", "#FFF8EE"),
    "Low": ("#34C759", "#F0FFF4"),
    "Immediate": ("#FF3B30", "#FFF0EF"),
    "Short-term": ("#FF9500", "#FFF8EE"),
    "Long-term": ("#34C759", "#F0FFF4"),
}


def severity_badge(level: str) -> str:
    color, bg = SEVERITY_COLORS.get(level, ("#666", "#f5f5f5"))
    return f'<span class="badge" style="background:{bg};color:{color};border:1px solid {color};">{level}</span>'


def get_image_tag(img_id: str, image_map: Dict, caption: str = "") -> str:
    img = image_map.get(img_id)
    if not img:
        return f'<div class="img-missing">Image Not Available ({img_id})</div>'
    
    data_uri = f"data:{img['mime']};base64,{img['b64']}"
    src_label = img.get("source", "")
    page_label = img.get("page", "")
    cap = caption or f"{src_label} – Page {page_label}"
    
    return f'''<figure class="report-figure">
        <img src="{data_uri}" alt="{cap}" loading="lazy" />
        <figcaption>{cap}</figcaption>
    </figure>'''


def render_metadata_section(meta: Dict) -> str:
    fields = [
        ("Property Address", meta.get("property_address", "Not Available")),
        ("Inspection Date", meta.get("inspection_date", "Not Available")),
        ("Inspected By", meta.get("inspected_by", "Not Available")),
        ("Property Type", meta.get("property_type", "Not Available")),
        ("Floors", meta.get("floors", "Not Available")),
        ("Previous Structural Audit", meta.get("previous_structural_audit", "Not Available")),
        ("Previous Repairs Done", meta.get("previous_repairs", "Not Available")),
        ("Thermal Imaging Device", meta.get("thermal_device", "Not Available")),
        ("Thermal Survey Date", meta.get("thermal_date", "Not Available")),
    ]
    rows = "".join(
        f'<tr><td class="meta-key">{k}</td><td class="meta-val">{v}</td></tr>'
        for k, v in fields
    )
    return f'<table class="meta-table">{rows}</table>'


def render_issue_summary(summary: Dict) -> str:
    areas = summary.get("affected_areas", [])
    areas_html = " ".join(f'<span class="tag">{a}</span>' for a in areas)
    return f'''
    <div class="summary-card">
        <p class="summary-text">{summary.get("overview", "Not Available")}</p>
        <div class="summary-stats">
            <div class="stat-box">
                <div class="stat-num">{summary.get("total_issues_found", "—")}</div>
                <div class="stat-label">Issues Found</div>
            </div>
            <div class="stat-box primary-concern">
                <div class="stat-label">Primary Concern</div>
                <div class="stat-concern">{summary.get("primary_concern", "Not Available")}</div>
            </div>
        </div>
        <div class="areas-wrap">
            <span class="areas-label">Affected Areas:</span>
            {areas_html}
        </div>
    </div>
    '''


def render_area_observations(observations: List[Dict], image_map: Dict) -> str:
    if not observations:
        return "<p>Not Available</p>"
    
    parts = []
    for i, obs in enumerate(observations):
        area = obs.get("area_name", f"Area {i+1}")
        severity = obs.get("severity", "Medium")
        badge = severity_badge(severity)
        
        # Images for this area
        assigned = obs.get("assigned_images", [])
        img_html = ""
        if assigned:
            img_html = '<div class="img-grid">' + "".join(
                get_image_tag(img_id, image_map) for img_id in assigned
            ) + '</div>'
        else:
            img_html = '<div class="img-missing">Image Not Available</div>'
        
        thermal = obs.get("thermal_reading", "Not Available")
        
        parts.append(f'''
        <div class="area-card">
            <div class="area-header">
                <h3 class="area-title">{area}</h3>
                {badge}
            </div>
            <div class="area-grid">
                <div class="area-col">
                    <div class="obs-label">🔴 Negative Side (Damage Observed)</div>
                    <p>{obs.get("negative_side", "Not Available")}</p>
                    
                    <div class="obs-label">🟢 Positive Side (Source Found)</div>
                    <p>{obs.get("positive_side", "Not Available")}</p>
                    
                    <div class="obs-label">🌡️ Thermal Reading</div>
                    <p class="thermal-chip">{thermal}</p>
                    
                    <div class="obs-label">👁️ Visual Observation</div>
                    <p>{obs.get("visual_description", "Not Available")}</p>
                </div>
                <div class="area-col img-col">
                    {img_html}
                </div>
            </div>
        </div>
        ''')
    
    return "\n".join(parts)


def render_root_causes(causes: List[Dict]) -> str:
    if not causes:
        return "<p>Not Available</p>"
    
    parts = []
    for i, cause in enumerate(causes):
        areas = ", ".join(cause.get("affected_areas", []))
        parts.append(f'''
        <div class="cause-item">
            <div class="cause-num">{i+1}</div>
            <div class="cause-body">
                <p class="cause-text">{cause.get("cause", "Not Available")}</p>
                <div class="cause-meta">
                    <span><strong>Affected Areas:</strong> {areas or "Not Available"}</span>
                    <span><strong>Evidence:</strong> {cause.get("evidence", "Not Available")}</span>
                </div>
            </div>
        </div>
        ''')
    
    return "\n".join(parts)


def render_severity_assessment(assessment: Dict) -> str:
    overall = assessment.get("overall_severity", "Medium")
    reasoning = assessment.get("reasoning", "Not Available")
    items = assessment.get("items", [])
    
    badge = severity_badge(overall)
    
    rows = ""
    for item in items:
        sev = item.get("severity", "Medium")
        b = severity_badge(sev)
        rows += f'''<tr>
            <td>{item.get("issue", "Not Available")}</td>
            <td>{b}</td>
            <td>{item.get("reason", "Not Available")}</td>
        </tr>'''
    
    table = f'''<table class="sev-table">
        <thead><tr><th>Issue</th><th>Severity</th><th>Reasoning</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>''' if rows else "<p>Not Available</p>"
    
    return f'''
    <div class="sev-overall">
        <span>Overall Severity: </span>{badge}
    </div>
    <p class="sev-reasoning">{reasoning}</p>
    {table}
    '''


def render_recommended_actions(actions: List[Dict]) -> str:
    if not actions:
        return "<p>Not Available</p>"
    
    # Group by priority
    priority_order = ["Immediate", "Short-term", "Long-term"]
    grouped = {p: [] for p in priority_order}
    
    for action in actions:
        priority = action.get("priority", "Short-term")
        if priority in grouped:
            grouped[priority].append(action)
        else:
            grouped["Short-term"].append(action)
    
    parts = []
    for priority in priority_order:
        items = grouped[priority]
        if not items:
            continue
        
        color, bg = SEVERITY_COLORS.get(priority, ("#666", "#f5f5f5"))
        rows = "".join(f'''
        <div class="action-item" style="border-left: 3px solid {color};">
            <div class="action-area">{action.get("area", "General")}</div>
            <div class="action-text">{action.get("action", "Not Available")}</div>
            <div class="action-method">{action.get("method", "")}</div>
        </div>
        ''' for action in items)
        
        parts.append(f'''
        <div class="action-group">
            <div class="action-group-header" style="background:{bg};color:{color};border:1px solid {color};">
                {priority} Action Required
            </div>
            {rows}
        </div>
        ''')
    
    return "\n".join(parts)


def render_list_section(items: List) -> str:
    if not items:
        return "<p>Not Available</p>"
    return "<ul class='plain-list'>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def render_ddr_html(ddr_data: Dict, image_map: Dict) -> str:
    """
    Render the full DDR as a self-contained HTML string.
    """
    meta = ddr_data.get("report_metadata", {})
    generated_on = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    address = meta.get("property_address", "Property Inspection Report")
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Detailed Diagnostic Report – {address}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --ink: #0D0D0D;
            --ink-light: #3D3D3D;
            --ink-faint: #7A7A7A;
            --paper: #FAFAF7;
            --surface: #FFFFFF;
            --border: #E5E5E0;
            --accent: #C8A96E;
            --accent-dark: #8B6914;
            --section-num: #C8A96E;
            --header-bg: #0D0D0D;
            --header-fg: #FAFAF7;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'DM Sans', sans-serif;
            background: var(--paper);
            color: var(--ink);
            font-size: 15px;
            line-height: 1.65;
        }}

        /* ========= HEADER ========= */
        .report-header {{
            background: var(--header-bg);
            color: var(--header-fg);
            padding: 48px 64px 40px;
            position: relative;
            overflow: hidden;
        }}
        .report-header::before {{
            content: '';
            position: absolute;
            top: -60px; right: -60px;
            width: 280px; height: 280px;
            border-radius: 50%;
            border: 1px solid rgba(200, 169, 110, 0.2);
        }}
        .report-header::after {{
            content: '';
            position: absolute;
            bottom: -80px; left: 40px;
            width: 200px; height: 200px;
            border-radius: 50%;
            border: 1px solid rgba(200, 169, 110, 0.1);
        }}
        .header-label {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 12px;
        }}
        .header-title {{
            font-family: 'DM Serif Display', serif;
            font-size: 38px;
            font-weight: 400;
            line-height: 1.15;
            max-width: 640px;
            margin-bottom: 24px;
        }}
        .header-title em {{
            color: var(--accent);
            font-style: italic;
        }}
        .header-meta-row {{
            display: flex;
            gap: 32px;
            flex-wrap: wrap;
            margin-top: 8px;
        }}
        .header-meta-item {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .header-meta-key {{
            font-size: 10px;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            color: rgba(250,250,247,0.5);
        }}
        .header-meta-val {{
            font-size: 14px;
            font-weight: 500;
            color: var(--header-fg);
        }}
        .header-divider {{
            height: 1px;
            background: linear-gradient(90deg, var(--accent) 0%, transparent 60%);
            margin: 28px 0 20px;
        }}
        .generated-stamp {{
            font-size: 12px;
            color: rgba(250,250,247,0.4);
            font-family: 'DM Mono', monospace;
        }}
        
        /* ========= LAYOUT ========= */
        .report-body {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 0 32px 80px;
        }}
        
        /* ========= SECTIONS ========= */
        .report-section {{
            margin-top: 56px;
        }}
        .section-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--border);
        }}
        .section-num {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            font-weight: 500;
            color: var(--accent-dark);
            background: #FDF5E6;
            border: 1px solid var(--accent);
            padding: 3px 8px;
            border-radius: 3px;
            letter-spacing: 0.1em;
        }}
        .section-title {{
            font-family: 'DM Serif Display', serif;
            font-size: 24px;
            font-weight: 400;
            color: var(--ink);
        }}
        
        /* ========= META TABLE ========= */
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }}
        .meta-table tr:nth-child(even) {{ background: #F7F7F4; }}
        .meta-key {{
            padding: 10px 16px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--ink-faint);
            width: 240px;
            border-right: 1px solid var(--border);
        }}
        .meta-val {{
            padding: 10px 16px;
            font-size: 14px;
            color: var(--ink);
        }}

        /* ========= SUMMARY CARD ========= */
        .summary-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 28px;
        }}
        .summary-text {{
            font-size: 16px;
            line-height: 1.7;
            color: var(--ink-light);
            margin-bottom: 24px;
        }}
        .summary-stats {{
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .stat-box {{
            background: #F7F7F4;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 20px;
            min-width: 160px;
        }}
        .stat-num {{
            font-family: 'DM Serif Display', serif;
            font-size: 40px;
            color: var(--accent-dark);
            line-height: 1;
        }}
        .stat-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--ink-faint);
            margin-top: 4px;
        }}
        .primary-concern {{
            flex: 1;
        }}
        .stat-concern {{
            font-size: 15px;
            font-weight: 600;
            color: var(--ink);
            margin-top: 6px;
        }}
        .areas-wrap {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .areas-label {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--ink-faint);
        }}
        .tag {{
            background: #F0EDE5;
            border: 1px solid #D4C9B0;
            color: var(--accent-dark);
            font-size: 12px;
            padding: 3px 10px;
            border-radius: 100px;
            font-weight: 500;
        }}
        
        /* ========= BADGE ========= */
        .badge {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            padding: 3px 10px;
            border-radius: 4px;
            white-space: nowrap;
        }}

        /* ========= AREA CARDS ========= */
        .area-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 24px;
        }}
        .area-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--border);
        }}
        .area-title {{
            font-family: 'DM Serif Display', serif;
            font-size: 20px;
            font-weight: 400;
        }}
        .area-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
            align-items: start;
        }}
        .obs-label {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--ink-faint);
            margin-top: 16px;
            margin-bottom: 4px;
        }}
        .obs-label:first-child {{ margin-top: 0; }}
        .thermal-chip {{
            font-family: 'DM Mono', monospace;
            font-size: 13px;
            background: #F0EEE8;
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 6px;
            display: inline-block;
        }}
        
        /* ========= IMAGES ========= */
        .img-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}
        .report-figure {{
            margin: 0;
        }}
        .report-figure img {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            border-radius: 6px;
            border: 1px solid var(--border);
            display: block;
        }}
        .report-figure figcaption {{
            font-size: 10px;
            color: var(--ink-faint);
            text-align: center;
            margin-top: 4px;
            font-family: 'DM Mono', monospace;
        }}
        .img-missing {{
            background: #F7F7F4;
            border: 1px dashed #C5C5C0;
            border-radius: 6px;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: var(--ink-faint);
            font-family: 'DM Mono', monospace;
        }}
        
        /* ========= ROOT CAUSES ========= */
        .cause-item {{
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
        }}
        .cause-num {{
            width: 36px;
            height: 36px;
            background: var(--ink);
            color: var(--header-fg);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'DM Serif Display', serif;
            font-size: 16px;
            flex-shrink: 0;
        }}
        .cause-body {{ flex: 1; }}
        .cause-text {{
            font-size: 15px;
            font-weight: 500;
            margin-bottom: 10px;
            line-height: 1.5;
        }}
        .cause-meta {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 13px;
            color: var(--ink-light);
        }}
        
        /* ========= SEVERITY ========= */
        .sev-overall {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .sev-reasoning {{
            color: var(--ink-light);
            margin-bottom: 20px;
            line-height: 1.65;
        }}
        .sev-table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }}
        .sev-table th {{
            background: #F7F7F4;
            padding: 10px 14px;
            text-align: left;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--ink-faint);
            border-bottom: 1px solid var(--border);
        }}
        .sev-table td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }}
        .sev-table tr:last-child td {{ border-bottom: none; }}
        .sev-table tr:nth-child(even) td {{ background: #FAFAF7; }}
        
        /* ========= ACTIONS ========= */
        .action-group {{ margin-bottom: 24px; }}
        .action-group-header {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            padding: 8px 14px;
            border-radius: 6px 6px 0 0;
            margin-bottom: 0;
        }}
        .action-item {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-top: none;
            padding: 16px 16px 16px 20px;
        }}
        .action-item:last-child {{ border-radius: 0 0 6px 6px; }}
        .action-area {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--ink-faint);
            margin-bottom: 4px;
        }}
        .action-text {{
            font-size: 15px;
            font-weight: 500;
            margin-bottom: 4px;
        }}
        .action-method {{
            font-size: 13px;
            color: var(--ink-light);
        }}
        
        /* ========= PLAIN LIST ========= */
        .plain-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .plain-list li {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px 16px;
            font-size: 14px;
            color: var(--ink-light);
            position: relative;
            padding-left: 28px;
        }}
        .plain-list li::before {{
            content: '→';
            position: absolute;
            left: 12px;
            color: var(--accent);
            font-weight: 700;
        }}
        
        /* ========= FOOTER ========= */
        .report-footer {{
            background: var(--ink);
            color: rgba(250,250,247,0.5);
            text-align: center;
            padding: 28px 40px;
            margin-top: 80px;
            font-size: 12px;
            font-family: 'DM Mono', monospace;
            line-height: 1.8;
        }}
        .footer-brand {{
            color: var(--accent);
            font-size: 14px;
            font-family: 'DM Serif Display', serif;
            font-weight: 400;
            margin-bottom: 4px;
        }}
        
        /* ========= RESPONSIVE ========= */
        @media (max-width: 768px) {{
            .report-header {{ padding: 32px 24px; }}
            .header-title {{ font-size: 28px; }}
            .report-body {{ padding: 0 16px 60px; }}
            .area-grid {{ grid-template-columns: 1fr; }}
            .img-grid {{ grid-template-columns: 1fr; }}
            .header-meta-row {{ gap: 16px; }}
        }}
    </style>
</head>
<body>

<!-- ===== HEADER ===== -->
<header class="report-header">
    <div class="header-label">UrbanRoof · Detailed Diagnostic Report</div>
    <h1 class="header-title">
        Property <em>Health</em><br>Diagnosis Report
    </h1>
    <div class="header-divider"></div>
    <div class="header-meta-row">
        <div class="header-meta-item">
            <span class="header-meta-key">Property</span>
            <span class="header-meta-val">{meta.get("property_address", "Not Available")}</span>
        </div>
        <div class="header-meta-item">
            <span class="header-meta-key">Inspection Date</span>
            <span class="header-meta-val">{meta.get("inspection_date", "Not Available")}</span>
        </div>
        <div class="header-meta-item">
            <span class="header-meta-key">Inspected By</span>
            <span class="header-meta-val">{meta.get("inspected_by", "Not Available")}</span>
        </div>
        <div class="header-meta-item">
            <span class="header-meta-key">Report Generated</span>
            <span class="header-meta-val">{generated_on}</span>
        </div>
    </div>
    <div style="margin-top:16px">
        <span class="generated-stamp">AI-Assisted Analysis · For Internal Use Only</span>
    </div>
</header>

<!-- ===== BODY ===== -->
<div class="report-body">

    <!-- SECTION 0: Inspection Details -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">00</span>
            <h2 class="section-title">Inspection Details</h2>
        </div>
        {render_metadata_section(meta)}
    </div>

    <!-- SECTION 1: Property Issue Summary -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">01</span>
            <h2 class="section-title">Property Issue Summary</h2>
        </div>
        {render_issue_summary(ddr_data.get("property_issue_summary", {{}}))}
    </div>

    <!-- SECTION 2: Area-wise Observations -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">02</span>
            <h2 class="section-title">Area-wise Observations</h2>
        </div>
        {render_area_observations(ddr_data.get("area_observations", []), image_map)}
    </div>

    <!-- SECTION 3: Probable Root Cause -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">03</span>
            <h2 class="section-title">Probable Root Cause</h2>
        </div>
        {render_root_causes(ddr_data.get("probable_root_causes", []))}
    </div>

    <!-- SECTION 4: Severity Assessment -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">04</span>
            <h2 class="section-title">Severity Assessment</h2>
        </div>
        {render_severity_assessment(ddr_data.get("severity_assessment", {{}}))}
    </div>

    <!-- SECTION 5: Recommended Actions -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">05</span>
            <h2 class="section-title">Recommended Actions</h2>
        </div>
        {render_recommended_actions(ddr_data.get("recommended_actions", []))}
    </div>

    <!-- SECTION 6: Additional Notes -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">06</span>
            <h2 class="section-title">Additional Notes</h2>
        </div>
        {render_list_section(ddr_data.get("additional_notes", []))}
    </div>

    <!-- SECTION 7: Missing or Unclear Information -->
    <div class="report-section">
        <div class="section-header">
            <span class="section-num">07</span>
            <h2 class="section-title">Missing or Unclear Information</h2>
        </div>
        {render_list_section(ddr_data.get("missing_or_unclear_information", []))}
    </div>

</div><!-- end report-body -->

<!-- ===== FOOTER ===== -->
<footer class="report-footer">
    <div class="footer-brand">UrbanRoof Private Limited</div>
    <div>AI-assisted Detailed Diagnostic Report · Generated {generated_on}</div>
    <div style="margin-top:6px;font-size:10px;">
        This report is based on visual inspection data and thermal imaging provided. 
        It is not an exhaustive structural audit. Consult a licensed engineer for critical structural decisions.
    </div>
</footer>

</body>
</html>'''
    
    return html
