"""
analyzer.py - DDR generation via OpenRouter (text-only, with working fallback)
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Any

FREE_MODELS = [
    "qwen/qwen2.5-vl-32b-instruct:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1-0528:free",
]


def build_prompt(inspection_text: str, thermal_text: str) -> str:
    return f"""You are a property inspection expert. Generate a Detailed Diagnostic Report (DDR) from the two documents below.

RULES:
- Only use facts present in the documents. Never invent data.
- If data is missing, write exactly: Not Available
- If data conflicts between documents, mention the conflict
- Use simple, client-friendly language
- Respond with ONLY a valid JSON object. No markdown. No code fences. No explanation. Start with {{ and end with }}.

=== INSPECTION REPORT ===
{inspection_text[:7000]}

=== THERMAL REPORT ===
{thermal_text[:3500]}

Return exactly this JSON structure with all fields filled from the documents:

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


def _try_model(api_key: str, model: str, prompt: str) -> str:
    """Call one model. Returns response text or raises exception."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://urbanroof-ddr.streamlit.app",
            "X-Title": "UrbanRoof DDR Generator",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    # Check for API-level error inside a 200 response
    if "error" in result:
        raise ValueError(result["error"].get("message", "Unknown API error"))

    return result["choices"][0]["message"]["content"].strip()


def call_gemini(
    api_key: str,
    inspection_text: str,
    thermal_text: str,
    all_images: List[Dict],
    inspection_image_ids: List[str],
    thermal_image_ids: List[str],
) -> Dict[str, Any]:
    """
    Generate DDR JSON via OpenRouter text-only call.
    Tries multiple free models in order until one succeeds.
    Images are embedded into the HTML report by the renderer directly.
    """
    prompt = build_prompt(inspection_text, thermal_text)

    errors = []
    raw = None

    for model in FREE_MODELS:
        try:
            raw = _try_model(api_key, model, prompt)
            # If we got a non-empty response, break
            if raw and len(raw) > 50:
                break
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            errors.append(f"{model}: HTTP {e.code} — {body}")
            raw = None
            continue
        except Exception as e:
            errors.append(f"{model}: {str(e)[:200]}")
            raw = None
            continue

    if not raw:
        raise ValueError(
            f"All models failed. Errors:\n" + "\n".join(errors)
        )

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to extract JSON substring
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        raise ValueError(
            f"Response not valid JSON.\nError: {e}\nFirst 600 chars:\n{raw[:600]}"
        )
