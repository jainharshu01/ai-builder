"""
analyzer.py - DDR generation via Google Gemini REST API
Uses v1 (stable) endpoint with current model names.
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Any

# Current confirmed model names as of 2025/2026
# Using v1 (stable) API endpoint, not v1beta
MODELS = [
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
]


def build_prompt(inspection_text: str, thermal_text: str) -> str:
    return f"""You are a property inspection expert. Generate a Detailed Diagnostic Report (DDR) from the two documents below.

RULES:
- Only use facts present in the documents. Never invent data.
- If data is missing, write exactly: Not Available
- If data conflicts between documents, mention the conflict explicitly
- Use simple, client-friendly language. No jargon.
- Respond with ONLY a valid JSON object. Absolutely no markdown, no code fences, no explanation text.
- Your response must start with the character {{ and end with the character }}

=== INSPECTION REPORT ===
{inspection_text[:7000]}

=== THERMAL REPORT ===
{thermal_text[:3500]}

Return exactly this JSON structure with every field populated from the documents above:

{{
  "report_metadata": {{
    "property_address": "full address or Not Available",
    "inspection_date": "date or Not Available",
    "inspected_by": "name or Not Available",
    "property_type": "Flat or House or Not Available",
    "floors": "number or Not Available",
    "previous_structural_audit": "Yes or No or Not Available",
    "previous_repairs": "Yes or No or Not Available",
    "thermal_device": "device name and serial number or Not Available",
    "thermal_date": "date or Not Available"
  }},
  "property_issue_summary": {{
    "overview": "3-4 sentence plain-language summary of all main problems found at this property",
    "total_issues_found": 7,
    "primary_concern": "the single most urgent issue in one sentence",
    "affected_areas": ["Hall", "Bedroom", "Master Bedroom", "Kitchen", "Parking Area", "Common Bathroom"]
  }},
  "area_observations": [
    {{
      "area_name": "Hall",
      "negative_side": "exact damage or symptom observed on the affected side from the inspection report",
      "positive_side": "exact finding on the source side from the inspection report",
      "thermal_reading": "Hotspot temperature and Coldspot temperature from thermal report, or Not Available",
      "visual_description": "description of what the site photographs show for this area",
      "severity": "High"
    }},
    {{
      "area_name": "Common Bedroom",
      "negative_side": "exact damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }},
    {{
      "area_name": "Master Bedroom",
      "negative_side": "exact damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "High"
    }},
    {{
      "area_name": "Kitchen",
      "negative_side": "exact damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }},
    {{
      "area_name": "Parking Area",
      "negative_side": "exact damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "High"
    }},
    {{
      "area_name": "Common Bathroom",
      "negative_side": "exact damage observed",
      "positive_side": "source finding",
      "thermal_reading": "temperatures or Not Available",
      "visual_description": "photo description",
      "severity": "Medium"
    }}
  ],
  "probable_root_causes": [
    {{
      "cause": "detailed root cause description",
      "affected_areas": ["list", "of", "areas"],
      "evidence": "specific evidence from the documents supporting this cause"
    }}
  ],
  "severity_assessment": {{
    "overall_severity": "High",
    "reasoning": "plain-language explanation of why this overall severity was assigned",
    "items": [
      {{
        "issue": "specific issue description",
        "severity": "High",
        "reason": "why this severity level was assigned"
      }}
    ]
  }},
  "recommended_actions": [
    {{
      "priority": "Immediate",
      "action": "specific action to take",
      "area": "which area this applies to",
      "method": "specific repair method from documents, or Not Available"
    }}
  ],
  "additional_notes": [
    "Any thermal imaging finding that adds diagnostic context not covered above",
    "Any conflict between the inspection report and thermal report",
    "Any other important observation"
  ],
  "missing_or_unclear_information": [
    "Customer name: Not provided in documents",
    "Property age: Not provided in documents",
    "List any other missing expected data here"
  ]
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
    Call Google Gemini REST API (v1, stable).
    Tries multiple current model names with full error reporting.
    """
    prompt = build_prompt(inspection_text, thermal_text)

    payload = json.dumps({
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        }
    }).encode("utf-8")

    all_errors = []
    raw = None

    for model in MODELS:
        # Use v1 (stable) endpoint
        url = (
            f"https://generativelanguage.googleapis.com"
            f"/v1/models/{model}:generateContent?key={api_key}"
        )
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # Check for blocked response
            if "candidates" not in result or not result["candidates"]:
                finish = result.get("promptFeedback", {}).get("blockReason", "no candidates")
                all_errors.append(f"{model}: blocked — {finish}")
                continue

            candidate = result["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                all_errors.append(f"{model}: empty parts in response")
                continue

            raw = parts[0].get("text", "").strip()
            if raw:
                break
            else:
                all_errors.append(f"{model}: empty text in response")

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = "(unreadable)"
            all_errors.append(f"{model}: HTTP {e.code} — {body[:300]}")
            continue
        except urllib.error.URLError as e:
            all_errors.append(f"{model}: URLError — {str(e)}")
            continue
        except Exception as e:
            all_errors.append(f"{model}: {type(e).__name__} — {str(e)[:200]}")
            continue

    if not raw:
        error_detail = "\n".join(f"  • {e}" for e in all_errors)
        raise ValueError(
            f"All Gemini models failed. Errors:\n{error_detail}\n\n"
            f"Check your API key is valid and billing is enabled at "
            f"console.cloud.google.com/billing"
        )

    # Strip markdown fences if model added them despite responseMimeType
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Try extracting JSON substring as last resort
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        raise ValueError(
            f"Model responded but output was not valid JSON.\n"
            f"JSON error: {e}\n"
            f"First 800 chars of response:\n{raw[:800]}"
        )
