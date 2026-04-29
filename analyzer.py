"""
analyzer.py - Send extracted content to an LLM for DDR generation
Uses OpenRouter API (free $1 credit on signup, no card needed)
Compatible with any OpenAI-format API
"""

import json
import re
import base64
import urllib.request
import urllib.error
from typing import Dict, List, Any


def build_system_prompt() -> str:
    return """You are an expert property inspection analyst at UrbanRoof, a building diagnostics company.
You specialize in generating Detailed Diagnostic Reports (DDR) by analyzing inspection data and thermal imaging.

STRICT RULES:
1. NEVER invent facts not present in the documents
2. If information conflicts between sources, explicitly mention the conflict
3. If information is missing, write "Not Available"
4. Use simple, client-friendly language - avoid jargon
5. Avoid duplicating observations

You must respond ONLY with a valid JSON object.
Start your response with { and end with }.
No markdown, no code fences, no explanation outside the JSON.
"""


def build_user_prompt(
    inspection_text: str,
    thermal_text: str,
    inspection_images: List[Dict],
    thermal_images: List[Dict],
) -> str:
    insp_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Inspection Report"
         for img in inspection_images]
    ) or "  None"

    thermal_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Thermal Report"
         for img in thermal_images]
    ) or "  None"

    return f"""You have inspection and thermal report data. Generate a complete DDR.

=== INSPECTION REPORT TEXT ===
{inspection_text[:6000]}

=== THERMAL REPORT TEXT ===
{thermal_text[:3000]}

=== INSPECTION IMAGE IDs ===
{insp_img_refs}

=== THERMAL IMAGE IDs ===
{thermal_img_refs}

Respond with ONLY this JSON structure (no markdown, no code fences):

{{
  "report_metadata": {{
    "property_address": "extracted or Not Available",
    "inspection_date": "extracted or Not Available",
    "inspected_by": "extracted or Not Available",
    "property_type": "extracted or Not Available",
    "floors": "extracted or Not Available",
    "previous_structural_audit": "extracted or Not Available",
    "previous_repairs": "extracted or Not Available",
    "thermal_device": "extracted or Not Available",
    "thermal_date": "extracted or Not Available"
  }},
  "property_issue_summary": {{
    "overview": "2-4 sentence plain-language summary",
    "total_issues_found": 7,
    "primary_concern": "the single most critical issue",
    "affected_areas": ["Hall", "Bedroom", "Master Bedroom", "Kitchen", "Parking", "Common Bathroom"]
  }},
  "area_observations": [
    {{
      "area_name": "Hall",
      "negative_side": "damage or symptom observed",
      "positive_side": "source found on positive side",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "what is visible in photos",
      "assigned_images": ["img_0"],
      "severity": "High"
    }}
  ],
  "probable_root_causes": [
    {{
      "cause": "root cause description",
      "affected_areas": ["Hall", "Bedroom"],
      "evidence": "evidence from the documents"
    }}
  ],
  "severity_assessment": {{
    "overall_severity": "High",
    "reasoning": "plain-language explanation",
    "items": [
      {{
        "issue": "issue description",
        "severity": "High",
        "reason": "reason for this severity"
      }}
    ]
  }},
  "recommended_actions": [
    {{
      "priority": "Immediate",
      "action": "what to do",
      "area": "where",
      "method": "how, from documents or Not Available"
    }}
  ],
  "additional_notes": ["note 1", "note 2"],
  "missing_or_unclear_information": ["item 1"]
}}

For assigned_images: only use IDs from the lists above. Assign each image to one area only.
"""


def call_gemini(
    api_key: str,
    inspection_text: str,
    thermal_text: str,
    all_images: List[Dict],
    inspection_image_ids: List[str],
    thermal_image_ids: List[str],
) -> Dict[str, Any]:
    """
    Call OpenRouter API with vision support.
    api_key should be your OpenRouter API key (from openrouter.ai).
    Uses google/gemini-2.0-flash-exp:free - genuinely free, no billing needed.
    """
    inspection_images = [img for img in all_images if img["id"] in inspection_image_ids]
    thermal_images = [img for img in all_images if img["id"] in thermal_image_ids]

    prompt_text = build_user_prompt(
        inspection_text=inspection_text,
        thermal_text=thermal_text,
        inspection_images=inspection_images,
        thermal_images=thermal_images,
    )

    # Build message content - text first, then images
    content = [{"type": "text", "text": build_system_prompt() + "\n\n" + prompt_text}]

    # Add images in OpenAI vision format
    for img in all_images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['mime']};base64,{img['b64']}"
            }
        })

    payload = {
        "model": "openrouter/free",
        "messages": [
            {"role": "user", "content": content}
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
    }

    payload_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload_bytes,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://urbanroof-ddr.streamlit.app",
            "X-Title": "UrbanRoof DDR Generator",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise ValueError(f"OpenRouter API error {e.code}: {error_body}")

    # Extract text from response
    raw_text = result["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if present
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)
    raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(
            f"Response was not valid JSON.\n\nError: {e}\n\nRaw (first 500 chars):\n{raw_text[:500]}"
        )
