"""
analyzer.py - DDR generation via Google Gemini API
Requires a Google AI Studio API key with billing linked.
Get one free at: aistudio.google.com
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Any


def build_prompt(inspection_text: str, thermal_text: str) -> str:
    return f"""You are a property inspection expert. Generate a Detailed Diagnostic Report (DDR) from the two documents below.

RULES:
- Only use facts present in the documents. Never invent data.
- If data is missing, write exactly: Not Available
- If data conflicts between documents, mention the conflict
- Use simple, client-friendly language
- Respond with ONLY a valid JSON object. No markdown. No code fences. Start with {{ and end with }}.

=== INSPECTION REPORT ===
{inspection_text[:7000]}

=== THERMAL REPORT ===
{thermal_text[:3500]}

Return exactly this JSON structure:

{{
  "report_metadata": {{
    "property_address": "full address or Not Available",
    "inspection_date": "date or Not Available",
    "inspected_by": "name or Not Available",
    "property_type": "Flat or House or Not Available",
    "floors": "number or Not Available",
    "previous_structural_audit": "Yes or No or Not Available",
    "previous_repairs": "Yes or No or Not Available",
    "thermal_device": "device name or Not Available",
    "thermal_date": "date or Not Available"
  }},
  "property_issue_summary": {{
    "overview": "3-4 sentence plain-language summary of all main problems",
    "total_issues_found": 7,
    "primary_concern": "the single most urgent issue",
    "affected_areas": ["Hall", "Bedroom", "Master Bedroom", "Kitchen", "Parking Area", "Common Bathroom"]
  }},
  "area_observations": [
    {{
      "area_name": "Hall",
      "negative_side": "damage or symptom observed",
      "positive_side": "finding on source side",
      "thermal_reading": "Hotspot X C, Coldspot Y C or Not Available",
      "visual_description": "what photos show for this area",
      "severity": "High"
    }},
    {{
      "area_name": "Common Bedroom",
      "negative_side": "damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }},
    {{
      "area_name": "Master Bedroom",
      "negative_side": "damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "High"
    }},
    {{
      "area_name": "Kitchen",
      "negative_side": "damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }},
    {{
      "area_name": "Parking Area",
      "negative_side": "damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "High"
    }},
    {{
      "area_name": "Common Bathroom",
      "negative_side": "damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }}
  ],
  "probable_root_causes": [
    {{
      "cause": "root cause description",
      "affected_areas": ["area1", "area2"],
      "evidence": "specific evidence from documents"
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
      "action": "specific action",
      "area": "which area",
      "method": "specific method or Not Available"
    }}
  ],
  "additional_notes": ["note 1", "note 2"],
  "missing_or_unclear_information": ["item 1", "item 2"]
}}"""


def call_gemini(
    api_key: str,
    inspection_text: str,
    thermal_text: str,
    all_images: List[Dict],
    inspection_image_ids: List[str],
    thermal_image_ids: List[str],
) -> Dict[str, Any]:
    """
    Call Google Gemini API directly via REST (no SDK dependency).
    api_key: Google AI Studio API key (aistudio.google.com)
    """
    prompt = build_prompt(inspection_text, thermal_text)

    payload = json.dumps({
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        }
    }).encode("utf-8")

    # Try models in order - newer ones first
    models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]

    last_error = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw:
                break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")[:400]
            last_error = f"{model}: HTTP {e.code} — {body}"
            continue
        except Exception as e:
            last_error = f"{model}: {str(e)[:200]}"
            continue
    else:
        raise ValueError(f"All Gemini models failed. Last error: {last_error}")

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        raise ValueError(
            f"Response not valid JSON.\nError: {e}\nFirst 600 chars:\n{raw[:600]}"
        )
