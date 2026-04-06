#!/usr/bin/env python3
"""
Strategist: trade-agnostic analyst that consumes inspector findings and
uses logic_weights from the trade fixture to decide if a finding is Critical.

Expected inspector_parser output (example):
{
  "id": "finding-123",
  "summary": "Found leak under sink",
  "details": "Water pooling under sink. Possible burst pipe."
}

The Strategist returns:
{
  "id": "...",
  "classification": "Critical" | "NonCritical",
  "score": N,
  "reasons": [...],
  "metadata": {...}
}
"""

from typing import Dict, Any, List, Tuple
import re
import logging

logger = logging.getLogger("botwave.strategist")
if not logger.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)


class Strategist:
    @staticmethod
    def normalize_keywords(keywords: List[Any]) -> List[Tuple[str, int]]:
        """
        Convert keywords list (strings or {term: weight}) to standardized (term, weight).
        """
        normalized = []
        for k in keywords or []:
            if isinstance(k, str):
                normalized.append((k.lower(), 1))
            elif isinstance(k, dict):
                if len(k) == 1:
                    term, weight = next(iter(k.items()))
                    try:
                        w = int(weight)
                    except Exception:
                        w = 1
                    normalized.append((term.lower(), w))
                else:
                    # unsupported dict format; flatten keys with weight=1
                    for term in k.keys():
                        normalized.append((term.lower(), 1))
            else:
                continue
        return normalized

    @staticmethod
    def score_finding(finding: Dict[str, Any], logic_weights: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a single inspector finding using logic_weights from the trade config.

        logic_weights schema expected:
          {
            "keywords": [ "leak", {"burst_pipe": 3} ],
            "high_priority_triggers": [ "no water", "gas smell" ],
            "critical_threshold": 3
          }
        """
        text = (" ".join([
            str(finding.get("summary", "")),
            str(finding.get("details", "")),
            " ".join(map(str, finding.get("tags", []) if isinstance(finding.get("tags", []), list) else []))
        ])).lower()

        keywords = logic_weights.get("keywords", [])
        normalized_keywords = Strategist.normalize_keywords(keywords)
        triggers = [t.lower() for t in (logic_weights.get("high_priority_triggers") or [])]
        threshold = logic_weights.get("critical_threshold", 3)

        score = 0
        reasons: List[str] = []

        # Count keyword matches (simple substring match; regex could be used)
        for term, weight in normalized_keywords:
            if term in text:
                score += weight
                reasons.append(f"keyword:{term} x{weight}")

        # Check triggers - these are high priority and add fixed jump (or immediate Critical marker)
        trigger_hits = []
        for trig in triggers:
            if trig in text:
                trigger_hits.append(trig)
                reasons.append(f"trigger:{trig}")

        # If any trigger hit, add extra weight (e.g., +critical_threshold)
        if trigger_hits:
            # Make triggers decisive by adding threshold
            bonus = threshold
            score += bonus
            logger.debug("Triggers hit: %s; adding bonus %s", trigger_hits, bonus)

        classification = "Critical" if score >= threshold else "NonCritical"

        result = {
            "id": finding.get("id"),
            "classification": classification,
            "score": score,
            "reasons": reasons,
            "metadata": {
                "trigger_hits": trigger_hits,
                "threshold": threshold,
            }
        }
        logger.info("Strategist evaluated finding %s -> %s (score=%s)", finding.get("id"), classification, score)
        return result