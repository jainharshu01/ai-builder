"""
analyzer.py - Send extracted content to Gemini for DDR generation
Uses the new google-genai SDK (google-genai package)
"""

from google import genai
from google.genai import types
import json
import re
from typing import Dict, List, Any


def build_system_prompt() -> str:
    return """You are an expert property inspection analyst at UrbanRoof, a building diagnostics company.
You specialize in generating Detailed Diagnostic Reports (DDR) by analyzing inspection data and thermal imaging.

Your task is to read inspection reports and thermal imaging data, then generate a structured, client-friendly DDR.

STRICT RULES:
1. NEVER invent facts not present in the documents
2. If information conflicts between sources, explicitly mention the conflict
3. If information is missing, write "Not Available"
4. Use simple, client-friendly language - avoid unnecessary jargon
5. Avoid duplicating the same observation in multiple places
6. Assign images to the most relevant section based on what is visually depicted

You must respond ONLY with a valid JSON object - no markdown, no code fences, no preamble, no explanation.
Start your response with { and end with }.
"""


def build_user_prompt(
    inspection_text: str,
    thermal_text: str,
    inspection_images: List[Dict],
    thermal_images: List[Dict],
) -> str:

    insp_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Inspection Report ({img['width']}x{img['height']}px)"
         for img in inspection_images]
    ) or "  None"

    thermal_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Thermal Report ({img['width']}x{img['height']}px)"
         for img in thermal_images]
    ) or "  None"

    return f"""You have been provided with:
1. TEXT from an Inspection Report
2. TEXT from a Thermal Imaging Report
3. IMAGES from both reports (their IDs are listed below)

=== INSPECTION REPORT TEXT ===
{inspection_text[:8000]}

=== THERMAL REPORT TEXT ===
{thermal_text[:4000]}

=== INSPECTION REPORT IMAGE IDs ===
{insp_img_refs}

=== THERMAL REPORT IMAGE IDs ===
{thermal_img_refs}

=== YOUR TASK ===
Generate a complete Detailed Diagnostic Report (DDR) merging both documents.

Respond with ONLY a JSON object in this EXACT structure:

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
    "overview": "2-4 sentence plain-language summary of the main problems found",
    "total_issues_found": 7,
    "primary_concern": "the single most critical issue",
    "affected_areas": ["Hall", "Bedroom", "Master Bedroom", "Kitchen", "Parking", "Common Bathroom"]
  }},
  "area_observations": [
    {{
      "area_name": "Hall",
      "negative_side": "What damage or symptom is visible on the affected side",
      "positive_side": "What was found on the source side",
      "thermal_reading": "Hotspot and coldspot temperatures if available, else Not Available",
      "visual_description": "What is visible in the photos for this area",
      "assigned_images": ["img_0", "img_1"],
      "severity": "High"
    }}
  ],
  "probable_root_causes": [
    {{
      "cause": "Description of root cause",
      "affected_areas": ["Hall", "Bedroom"],
      "evidence": "What evidence from the reports supports this"
    }}
  ],
  "severity_assessment": {{
    "overall_severity": "High",
    "reasoning": "Plain-language explanation of the overall severity rating",
    "items": [
      {{
        "issue": "Issue description",
        "severity": "High",
        "reason": "Why this severity was assigned"
      }}
    ]
  }},
  "recommended_actions": [
    {{
      "priority": "Immediate",
      "action": "What to do",
      "area": "Where",
      "method": "How, if described in the documents"
    }}
  ],
  "additional_notes": [
    "Any important observation not covered above",
    "Any conflicts between the two documents"
  ],
  "missing_or_unclear_information": [
    "Anything expected but not found in the documents"
  ]
}}

RULES for assigned_images:
- Only use image IDs from the lists above
- Assign each image to the ONE area it best matches visually
- Do not assign the same image to multiple areas
- If unsure where an image belongs, leave it out
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
    Call Gemini using the new google-genai SDK.
    Returns parsed DDR JSON dict.
    """
    client = genai.Client(api_key=api_key)

    inspection_images = [img for img in all_images if img["id"] in inspection_image_ids]
    thermal_images = [img for img in all_images if img["id"] in thermal_image_ids]

    prompt_text = build_user_prompt(
        inspection_text=inspection_text,
        thermal_text=thermal_text,
        inspection_images=inspection_images,
        thermal_images=thermal_images,
    )

    # Build parts: combined prompt text first, then all images
    parts = [types.Part(text=build_system_prompt() + "\n\n" + prompt_text)]
    for img in all_images:
        parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type=img["mime"],
                    data=img["b64"],
                )
            )
        )

    contents = [types.Content(role="user", parts=parts)]

    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )

    raw_text = response.text.strip()

    # Strip markdown fences if model added them anyway
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
            f"Gemini response was not valid JSON.\n\nError: {e}\n\nRaw response (first 500 chars):\n{raw_text[:500]}"
        )
