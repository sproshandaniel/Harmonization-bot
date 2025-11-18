"""
Real Rule Extraction Pipeline
-----------------------------
Uses OpenAI GPT for rule synthesis and embeddings for duplicate detection.
"""

import os
import yaml
import numpy as np
from openai import OpenAI
from typing import Dict, Any
from dotenv import load_dotenv
import os
load_dotenv() 


# Initialize client (uses OPENAI_API_KEY environment variable)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -----------------------------------------------------------------------------
# PROMPT TEMPLATES
# -----------------------------------------------------------------------------
CODE_RULE_PROMPT = """
You are an ABAP code quality assistant.  
Given a code snippet or standard text, extract one enforceable governance rule.

Respond ONLY in valid YAML with these fields:
id, type (code|design|naming|performance|template), title, severity,
description, selector (pattern), fix (snippet), examples (good/bad),
rationale, confidence.

Code or text:
"""

DESIGN_RULE_PROMPT = """
You are a software architecture assistant.
Analyze this design or guideline paragraph and produce ONE rule in YAML:
id, type, title, severity, enforces, template, rationale, confidence.

Guideline:
"""


def detect_category(text: str) -> str:
    up = text.upper()
    if any(k in up for k in ["SELECT", "TRY.", "METHOD", "CALL FUNCTION"]):
        return "code"
    if "DESIGN" in up or "PATTERN" in up:
        return "design"
    if "NAME" in up or "PREFIX" in up:
        return "naming"
    if "PERFORMANCE" in up or "OPTIMIZE" in up:
        return "performance"
    if "TEMPLATE" in up or "SNIPPET" in up:
        return "template"
    return "code"

def cosine_similarity(a, b):
    """Cosine similarity between two vectors."""
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ---------------------------------------------------------------------------
# In-memory rule registry (acts as a mini vector database)
# ---------------------------------------------------------------------------
RULE_MEMORY: Dict[str, Dict[str, Any]] = {
    # Example existing rule
    "abap.db.no_select_star": {
        "yaml": "id: abap.db.no_select_star\ntype: code\nselector:\n  pattern: 'SELECT *'",
        "vector": None,
    }
}

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------
async def extract_rule_pipeline(raw_text: str):
    """
    Generate a rule YAML using GPT and detect duplicates using embeddings.
    Returns dict with yaml, confidence, duplicate_of, similarity.
    """
    category = detect_category(raw_text)
    prompt = CODE_RULE_PROMPT if category == "code" else DESIGN_RULE_PROMPT
    prompt = prompt.format(content=raw_text[:4000])

    try:
        # 1️⃣ Generate YAML with GPT
        completion = client.responses.create(
            model="gpt-4o-mini",
            input=prompt,
            temperature=0.2,
            max_output_tokens=800,
        )
        rule_yaml = completion.output_text.strip()

        # 2️⃣ Validate YAML structure
        try:
            rule_obj = yaml.safe_load(rule_yaml)
        except Exception as e:
            print("⚠️ YAML parse error:", e)
            rule_obj = None

        # 3️⃣ Compute embedding for duplicate detection
        emb_text = rule_yaml if rule_obj is None else f"{rule_obj.get('title','')} {rule_obj.get('description','')} {rule_obj.get('selector','')}"
        embedding = (
            client.embeddings.create(model="text-embedding-3-small", input=emb_text)
            .data[0]
            .embedding
        )

        # 4️⃣ Compare with memory to find duplicates
        duplicate_id = None
        similarity = 0.0
        for rid, data in RULE_MEMORY.items():
            if data.get("vector") is None:
                continue
            sim = cosine_similarity(embedding, data["vector"])
            if sim > similarity:
                similarity = sim
                if sim > 0.88:
                    duplicate_id = rid

        # 5️⃣ Store the new rule for future checks
        new_id = (
            rule_obj.get("id")
            if rule_obj and "id" in rule_obj
            else f"rule_{len(RULE_MEMORY)+1}"
        )
        RULE_MEMORY[new_id] = {"yaml": rule_yaml, "vector": embedding}

        # 6️⃣ Return structured response
        return {
            "yaml": rule_yaml,
            "confidence": rule_obj.get("confidence", 0.9) if rule_obj else 0.7,
            "duplicate_of": duplicate_id,
            "similarity": similarity if duplicate_id else None,
        }

    except Exception as e:
        # Fallback if anything fails
        print("❌ Extraction error:", e)
        fallback_yaml = f"""id: abap.generic.rule
type: code
title: Extraction failed
description: "{str(e)}"
confidence: 0.2
"""
        return {
            "yaml": fallback_yaml,
            "confidence": 0.2,
            "duplicate_of": None,
            "similarity": None,
        }
