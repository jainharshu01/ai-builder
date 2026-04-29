"""
analyzer.py - DDR generation via OpenRouter (text-only LLM call)
Images are extracted separately and placed in the HTML report by the renderer.
This avoids all base64 image transmission issues with free models.
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Any

# Priority-ordered list of free vision/text models on OpenRouter.
# We try each in order until one succeeds.
FREE_MODELS = [
    "qwen/qwen2.5-vl-32b-instruct:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


def build_prompt(inspection_text: str, thermal_text: str) -> str:
    return f"""You are an expert property inspection analyst. Generate a Detailed Diagnostic Report (DDR) by merging the two documents below.

STRICT RULES:
- NEVER invent facts not in the documents
- If data is missing write exactly: Not Available
- If data conflicts between documents, mention the conflict explicitly
- Use simple client-friendly language, avoid jargon
- Do not duplicate observations across sections
- Respond with ONLY a valid JSON object. No markdown, no code fences, no text before or after the JSON.

=== INSPECTION REPORT ===
{inspection_text[:7000]}

=== THERMAL REPORT ===
{thermal_text[:3500]}

Generate this exact JSON structure (fill every field from the documents above):

{{
  "report_metadata": {{
    "property_address": "full address or Not Available",
    "inspection_date": "date or Not Available",
    "inspected_by": "name(s) or Not Available",
    "property_type": "Flat/House/etc or Not Available",
    "floors": "number or Not Available",
    "previous_structural_audit": "Yes/No or Not Available",
    "previous_repairs": "Yes/No or Not Available",
    "thermal_device": "device name or Not Available",
    "thermal_date": "date or Not Available"
  }},
  "property_issue_summary": {{
    "overview": "3-4 sentence plain-language summary of all main problems found",
    "total_issues_found": 7,
    "primary_concern": "the single most urgent issue in one sentence",
    "affected_areas": ["Hall", "Bedroom", "Master Bedroom", "Kitchen", "Parking Area", "Common Bathroom"]
  }},
  "area_observations": [
    {{
      "area_name": "Hall",
      "negative_side": "exact damage or symptom observed on the affected side",
      "positive_side": "exact finding on the source side",
      "thermal_reading": "Hotspot X°C, Coldspot Y°C or Not Available",
      "visual_description": "what the photos show for this area",
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
      "affected_areas": ["list of areas"],
      "evidence": "specific evidence from the documents"
    }}
  ],
  "severity_assessment": {{
    "overall_severity": "High",
    "reasoning": "plain-language explanation of why this overall severity was assigned",
    "items": [
      {{
        "issue": "specific issue description",
        "severity": "High",
        "reason": "why this severity level"
      }}
    ]
  }},
  "recommended_actions": [
    {{
      "priority": "Immediate",
      "action": "specific action to take",
      "area": "which area",
      "method": "specific method from documents or Not Available"
    }}
  ],
  "additional_notes": [
    "Any thermal reading that adds diagnostic context",
    "Any conflict between inspection and thermal documents",
    "Any observation that doesn't fit other sections"
  ],
  "missing_or_unclear_information": [
    "Customer name: Not Available in documents",
    "Property age: Not Available in documents"
  ]
}}"""


def _call_openrouter(api_key: str, model: str, prompt: str) -> str:
    """Make a single text-only call to OpenRouter. Returns raw response text."""
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
    Generate DDR JSON by calling OpenRouter with text only.
    Images are NOT sent to the LLM — they are embedded in the HTML
    report directly by the renderer (page-ordered, by area).
    Returns parsed DDR JSON dict.
    """
    prompt = build_prompt(inspection_text, thermal_text)

    last_error = None
    for model in FREE_MODELS:
        try:
            raw = _call_openrouter(api_key, model, prompt)
            break
        except urllib.error.HTTPError as e:
            last_error = f"Model {model} failed: {e.code} {e.read().decode('utf-8')[:200]}"
            continue
        except Exception as e:
            last_error = f"Model {model} failed: {str(e)}"
            continue
    else:
        raise ValueError(f"All free models failed. Last error: {last_error}")

    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(
            f"Response was not valid JSON.\nError: {e}\nRaw (first 600 chars):\n{raw[:600]}"
        )
