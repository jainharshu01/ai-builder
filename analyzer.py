"""
analyzer.py - Send extracted content to Gemini 2.0 Flash for DDR generation
"""

import google.generativeai as genai
import json
import base64
import re
from typing import Dict, List, Any


def configure_gemini(api_key: str):
    genai.configure(api_key=api_key)


def build_system_prompt() -> str:
    return """You are an expert property inspection analyst at UrbanRoof, a building diagnostics company. 
You specialize in generating Detailed Diagnostic Reports (DDR) by analyzing inspection data and thermal imaging.

Your task is to read inspection reports and thermal imaging data, then generate a structured, client-friendly DDR.

STRICT RULES:
1. NEVER invent facts not present in the documents
2. If information conflicts between sources → explicitly mention the conflict
3. If information is missing → write "Not Available"
4. Use simple, client-friendly language — avoid unnecessary jargon
5. Avoid duplicating the same observation in multiple places
6. Assign images to the most relevant section based on what is visually depicted

You must respond ONLY with a valid JSON object (no markdown, no code fences, no preamble).
"""


def build_user_prompt(
    inspection_text: str,
    thermal_text: str,
    inspection_images: List[Dict],
    thermal_images: List[Dict],
) -> str:
    
    # Build image reference tables so the model knows what images exist
    insp_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Inspection Report ({img['width']}x{img['height']}px)"
         for img in inspection_images]
    )
    thermal_img_refs = "\n".join(
        [f"  - {img['id']}: Page {img['page']} of Thermal Report ({img['width']}x{img['height']}px)"
         for img in thermal_images]
    )
    
    return f"""
You have been provided with:
1. TEXT from an Inspection Report
2. TEXT from a Thermal Imaging Report
3. IMAGES from the Inspection Report (labeled with their IDs below)
4. IMAGES from the Thermal Report (labeled with their IDs below)

=== INSPECTION REPORT TEXT ===
{inspection_text}

=== THERMAL REPORT TEXT ===
{thermal_text}

=== AVAILABLE INSPECTION REPORT IMAGE IDs ===
{insp_img_refs if insp_img_refs else "None"}

=== AVAILABLE THERMAL REPORT IMAGE IDs ===
{thermal_img_refs if thermal_img_refs else "None"}

=== YOUR TASK ===
Generate a complete Detailed Diagnostic Report (DDR) by merging both documents intelligently.

Respond with ONLY a JSON object in this EXACT structure (no markdown, no code fences):

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
    "total_issues_found": number,
    "primary_concern": "the single most critical issue",
    "affected_areas": ["list", "of", "affected", "rooms/areas"]
  }},
  "area_observations": [
    {{
      "area_name": "e.g. Hall / Bedroom / Master Bedroom",
      "negative_side": "What damage/symptom is visible on the negative (affected) side",
      "positive_side": "What was found on the positive (source) side",
      "thermal_reading": "Hotspot and coldspot temperatures if available, else Not Available",
      "visual_description": "What is visible in the photos for this area",
      "assigned_images": ["img_0", "img_1"],
      "severity": "High / Medium / Low"
    }}
  ],
  "probable_root_causes": [
    {{
      "cause": "Description of root cause",
      "affected_areas": ["area1", "area2"],
      "evidence": "What evidence from the reports supports this"
    }}
  ],
  "severity_assessment": {{
    "overall_severity": "High / Medium / Low",
    "reasoning": "Plain-language explanation of why this severity was assigned",
    "items": [
      {{
        "issue": "Issue description",
        "severity": "High / Medium / Low",
        "reason": "Why this severity"
      }}
    ]
  }},
  "recommended_actions": [
    {{
      "priority": "Immediate / Short-term / Long-term",
      "action": "What to do",
      "area": "Where",
      "method": "How (if available from documents)"
    }}
  ],
  "additional_notes": [
    "Any important notes not covered above",
    "Conflicts between the two documents if any",
    "Observations from thermal imaging that add context"
  ],
  "missing_or_unclear_information": [
    "List anything that was expected but missing",
    "List any conflicting data points"
  ]
}}

IMPORTANT for assigned_images:
- Only use image IDs from the lists provided above
- Assign images to the area_observation that best matches what is depicted
- Each image should be assigned to at most ONE area
- Thermal images (from Thermal Report) should be preferentially assigned to the area matching their thermal reading location
- If you cannot determine where an image belongs, do NOT include it
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
    Call Gemini 2.0 Flash with multimodal input (text + images).
    Returns parsed DDR JSON dict.
    """
    configure_gemini(api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=build_system_prompt(),
    )
    
    # Separate images by source
    inspection_images = [img for img in all_images if img["id"] in inspection_image_ids]
    thermal_images = [img for img in all_images if img["id"] in thermal_image_ids]
    
    # Build user prompt text
    prompt_text = build_user_prompt(
        inspection_text=inspection_text,
        thermal_text=thermal_text,
        inspection_images=inspection_images,
        thermal_images=thermal_images,
    )
    
    # Build content parts: text first, then images
    content_parts = [{"text": prompt_text}]
    
    # Add images as inline data parts
    for img in all_images:
        content_parts.append({
            "inline_data": {
                "mime_type": img["mime"],
                "data": img["b64"],
            }
        })
    
    # Call the model
    response = model.generate_content(
        content_parts,
        generation_config={
            "temperature": 0.1,   # Low temperature for factual accuracy
            "max_output_tokens": 8192,
        }
    )
    
    raw_text = response.text.strip()
    
    # Strip markdown code fences if model added them despite instructions
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)
    raw_text = raw_text.strip()
    
    # Parse JSON
    try:
        ddr_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        # Attempt to extract JSON from response if there's surrounding text
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            ddr_data = json.loads(json_match.group())
        else:
            raise ValueError(f"Gemini response was not valid JSON: {e}\n\nRaw response:\n{raw_text[:500]}")
    
    return ddr_data
