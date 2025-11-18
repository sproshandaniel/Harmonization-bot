"""
Rule extraction pipeline using a free Hugging Face model.
"""

import yaml
import numpy as np
from transformers import pipeline
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Load a lightweight free model (runs locally; first load may take 1-2 min)
# ---------------------------------------------------------------------------
# For CPU machines, smaller models like 'google/flan-t5-base' or 'tiiuae/falcon-7b-instruct'
# work fine.  You can change this to any text-generation or instruction model you prefer.
model_name = "google/flan-t5-base"
generator = pipeline("text2text-generation", model=model_name)

# ---------------------------------------------------------------------------
# Simple in-memory duplicate store
# ---------------------------------------------------------------------------
RULE_MEMORY: Dict[str, Dict[str, Any]] = {}

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------
async def extract_rule_pipeline(raw_text: str):
    """
    Generate a YAML-style rule using a free Hugging Face model.
    """
    try:
        prompt = (
            "You are an ABAP code reviewer.  "
            "From the following code or text, extract ONE governance rule "
            "in YAML with fields: id, type, title, severity, description, "
            "selector, fix, examples, rationale.\n\n"
            f"Text:\n{raw_text}\n\nYAML Rule:"
        )

        output = generator(prompt, max_new_tokens=300, temperature=0.3)[0]["generated_text"]
        rule_yaml = output.strip()

        # Validate YAML
        try:
            rule_obj = yaml.safe_load(rule_yaml)
        except Exception:
            rule_obj = None

        # Simple duplicate check: compare text similarity to previous rules
        duplicate_id = None
        best_sim = 0.0
        for rid, entry in RULE_MEMORY.items():
            sim = cosine_similarity(
                np.frombuffer(entry["yaml"].encode(), dtype=np.uint8),
                np.frombuffer(rule_yaml.encode(), dtype=np.uint8),
            )
            if sim > best_sim:
                best_sim = sim
                if sim > 0.9:
                    duplicate_id = rid

        rule_id = (
            rule_obj.get("id", f"rule_{len(RULE_MEMORY)+1}") if rule_obj else f"rule_{len(RULE_MEMORY)+1}"
        )
        RULE_MEMORY[rule_id] = {"yaml": rule_yaml}

        return {
            "yaml": rule_yaml,
            "confidence": 0.8,
            "duplicate_of": duplicate_id,
            "similarity": best_sim if duplicate_id else None,
        }

    except Exception as e:
        print("❌ Extraction error:", e)
        fallback = f"""id: abap.generic.rule
type: code
title: Extraction failed
description: "{str(e)}"
confidence: 0.2
"""
        return {
            "yaml": fallback,
            "confidence": 0.2,
            "duplicate_of": None,
            "similarity": None,
        }
