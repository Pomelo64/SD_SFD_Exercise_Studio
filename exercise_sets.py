"""
exercise_sets.py — where the exercises come from.

An exercise set is one JSON document (format "bluejay-sfd-exercises",
version 1). The same format serves the built-in set, sets the AI generates
for a domain, and sets a lecturer writes and shares with students:

{
  "format": "bluejay-sfd-exercises", "version": 1,
  "title": "Water and cities", "domain": "urban water", "author": "…",
  "reveal_answers": "after_submit" | "never",
  "exercises": [
    {"id": "…", "title": "…", "difficulty": "Level 1 · Warm-up",
     "scenario": "the text the student reads",
     "expected_concepts": ["teaching point", …],        # the rubric
     "solution": {"stocks": [{"label"}], "flows": [{"label","from","to"}],
                  "auxiliaries": [{"label"}], "clouds": [{"label"}],
                  "connectors": [{"from","to"}]},       # the answer (optional)
     "tutor_notes": "what to accept, what to insist on"  # optional
    }
  ]
}

A bare list of exercises (like exercises/exercises.json) is accepted too.
With a "solution", the AI tutor grades against that answer — the lecturer's
idea of the model — instead of its own.
"""

import json
import os
import random
import re
from typing import Dict, List, Optional, Tuple

import llm_client

FORMAT = "bluejay-sfd-exercises"
_HERE = os.path.dirname(os.path.abspath(__file__))

# The ladder the built-in set follows; generated sets follow it too.
LEVELS = [
    ("Level 1 · Warm-up",
     "The minimal SFD: ONE stock, one inflow from a cloud and one outflow to a cloud. "
     "No auxiliaries, no connectors."),
    ("Level 2 · Basic",
     "One stock and one flow whose rate depends on the stock and on one or two "
     "auxiliaries through information connectors, closing a single feedback loop."),
    ("Level 3 · Developing",
     "One stock with BOTH an inflow and an outflow, each driven by the stock and its own "
     "rate-constant auxiliary through connectors (two feedback loops)."),
    ("Level 4 · Intermediate",
     "A goal-seeking loop: a target (auxiliary), the gap between target and stock "
     "(auxiliary), and a corrective flow driven by the gap, possibly with an adjustment "
     "time (auxiliary)."),
    ("Level 5 · Challenging",
     "TWO stocks joined by a stock-to-stock flow (material moves from one stock to the "
     "other), with the auxiliaries and connectors that set that flow's rate."),
    ("Level 6 · Advanced",
     "Two stocks, about four flows and several interacting feedback loops, with the "
     "auxiliaries the scenario needs."),
]
QUICK = [0, 2, 4]          # three exercises: levels 1, 3 and 5

# The app picks one of these when the student lets it decide.
DOMAINS = [
    "a coral reef", "a city's housing market", "a hospital emergency department",
    "a startup's customer base", "groundwater in a farming region", "a fishery",
    "a university's student enrolment", "a forest and wildfires", "a video game's players",
    "a bakery's stock of bread", "a country's public debt", "an online community",
    "a vaccination campaign", "a river reservoir", "a smartphone's battery charge",
    "a recycling programme", "a library's book collection", "a factory's spare parts",
    "a social-media rumour", "a national park's visitors", "a household's savings",
    "a beehive", "electric cars and charging stations", "a language spreading in a town",
    "a football club's fans", "plastic in the ocean", "a city's bike-sharing scheme",
    "a team's knowledge and staff turnover", "a coffee shop's queue", "carbon in the atmosphere",
]


# ---------------------------------------------------------------------------
# Loading and checking
# ---------------------------------------------------------------------------
def load_default() -> Dict:
    with open(os.path.join(_HERE, "exercises", "exercises.json"), encoding="utf-8") as fh:
        exs = json.load(fh)
    return {"format": FORMAT, "version": 1, "title": "The SFD ladder (built-in)",
            "source": "default", "domain": "", "reveal_answers": "after_submit",
            "exercises": exs}


def _labels(items) -> List[str]:
    return [str((x or {}).get("label", "")).strip() for x in items or [] if isinstance(x, dict)]


def check_solution(sol: Dict) -> List[str]:
    """Problems with a reference SFD (empty list = fine)."""
    if not isinstance(sol, dict):
        return ["the answer is not a diagram"]
    probs = []
    stocks, auxes, clouds = _labels(sol.get("stocks")), _labels(sol.get("auxiliaries")), \
        _labels(sol.get("clouds"))
    flows = [f for f in sol.get("flows") or [] if isinstance(f, dict)]
    flow_names = [str(f.get("label", "")).strip() for f in flows]
    if not stocks:
        probs.append("no stock")
    names = stocks + auxes + clouds + flow_names
    dup = {n for n in names if n and names.count(n) > 1}
    if dup:
        probs.append("names used twice: " + ", ".join(sorted(dup)))
    if any(not n for n in names):
        probs.append("an element without a name")
    ends = set(stocks) | set(clouds)
    for f in flows:
        for side in ("from", "to"):
            if str(f.get(side, "")).strip() not in ends:
                probs.append(f"flow “{f.get('label')}” {side} “{f.get(side)}”, "
                             "which is not a stock or cloud")
    for s in stocks:
        if not any(s in (f.get("from"), f.get("to")) for f in flows):
            probs.append(f"stock “{s}” has no flow")
    known = set(names)
    for c in sol.get("connectors") or []:
        if not isinstance(c, dict) or c.get("from") not in known or c.get("to") not in known:
            probs.append(f"connector {c.get('from') if isinstance(c, dict) else c} → "
                         f"{c.get('to') if isinstance(c, dict) else ''} names an unknown element")
    return probs


def _clean_solution(sol: Dict) -> Dict:
    out = {k: [] for k in ("stocks", "flows", "auxiliaries", "clouds", "connectors")}
    for k in ("stocks", "auxiliaries", "clouds"):
        out[k] = [{"label": str(x["label"]).strip()} for x in sol.get(k) or []
                  if isinstance(x, dict) and str(x.get("label", "")).strip()]
    out["flows"] = [{"label": str(f.get("label", "")).strip(),
                     "from": str(f.get("from", "")).strip(), "to": str(f.get("to", "")).strip()}
                    for f in sol.get("flows") or [] if isinstance(f, dict)]
    out["connectors"] = [{"from": str(c.get("from", "")).strip(), "to": str(c.get("to", "")).strip()}
                         for c in sol.get("connectors") or [] if isinstance(c, dict)]
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:40] or "exercise"


def normalise(data, source: str) -> Tuple[Optional[Dict], List[str], List[str]]:
    """Check an exercise set (a lecturer's file or the AI's). Returns
    (set or None, errors, warnings). Exercises with a broken answer are kept
    without it, with a warning — the rubric still guides the tutor."""
    errors, warns = [], []
    if isinstance(data, list):
        data = {"exercises": data}
    if not isinstance(data, dict) or not isinstance(data.get("exercises"), list):
        return None, ["The file has no list of “exercises”."], []
    exs = []
    for n, ex in enumerate(data["exercises"], 1):
        if not isinstance(ex, dict):
            errors.append(f"Exercise {n} is not an object.")
            continue
        scen = str(ex.get("scenario", "")).strip()
        if not scen:
            errors.append(f"Exercise {n} has no “scenario” (the text students read).")
            continue
        concepts = ex.get("expected_concepts") or []
        if isinstance(concepts, str):
            concepts = [concepts]
        concepts = [str(c).strip() for c in concepts if str(c).strip()]
        title = str(ex.get("title") or f"Exercise {n}").strip()
        item = {"id": str(ex.get("id") or f"{_slug(title)}_{n}"),
                "type": "sfd", "title": title,
                "difficulty": str(ex.get("difficulty") or "").strip(),
                "scenario": scen, "expected_concepts": concepts}
        if ex.get("tutor_notes"):
            item["tutor_notes"] = str(ex["tutor_notes"]).strip()
        if ex.get("solution") is not None:
            probs = check_solution(ex["solution"])
            if probs:
                warns.append(f"“{title}”: the answer diagram was left out ("
                             + "; ".join(probs[:3]) + ").")
            else:
                item["solution"] = _clean_solution(ex["solution"])
        if not concepts and "solution" not in item:
            warns.append(f"“{title}” has neither teaching points nor an answer; the tutor "
                         "will grade it from the scenario alone.")
        exs.append(item)
    ids = [e["id"] for e in exs]
    for i, e in enumerate(exs):                     # ids must be unique
        if ids.count(e["id"]) > 1:
            e["id"] = f"{e['id']}_{i + 1}"
    if not exs:
        return None, errors or ["The file has no usable exercises."], warns
    reveal = data.get("reveal_answers", "after_submit")
    if reveal not in ("after_submit", "never"):
        reveal = "after_submit"
    return ({"format": FORMAT, "version": 1,
             "title": str(data.get("title") or "Imported exercises"),
             "domain": str(data.get("domain") or ""), "author": str(data.get("author") or ""),
             "source": source, "reveal_answers": reveal, "exercises": exs},
            errors, warns)


def export(ex_set: Dict) -> str:
    keep = {k: ex_set.get(k) for k in ("format", "version", "title", "domain", "author",
                                       "reveal_answers") if ex_set.get(k) not in (None, "")}
    keep["exercises"] = ex_set["exercises"]
    return json.dumps(keep, indent=2, ensure_ascii=False)


TEMPLATE = {
    "format": FORMAT, "version": 1,
    "title": "My exercises", "domain": "", "author": "Your name",
    "reveal_answers": "after_submit",
    "exercises": [{
        "id": "bathtub",
        "title": "1 · The Bathtub",
        "difficulty": "Level 1 · Warm-up",
        "scenario": "A bathtub is filled from the tap while the drain is open. Draw it as "
                    "a Stock and Flow Diagram: what accumulates, what fills it, what drains it?",
        "expected_concepts": [
            "The STOCK is the Water in the tub.",
            "Filling is an INFLOW from a CLOUD into the stock; draining is an OUTFLOW to a CLOUD.",
            "No auxiliaries or connectors are needed."],
        "solution": {
            "stocks": [{"label": "Water in tub"}],
            "flows": [{"label": "filling", "from": "tap", "to": "Water in tub"},
                      {"label": "draining", "from": "Water in tub", "to": "drain"}],
            "auxiliaries": [],
            "clouds": [{"label": "tap"}, {"label": "drain"}],
            "connectors": []},
        "tutor_notes": "Accept any name for the stock. Insist that the water is a stock, "
                       "not an auxiliary."}]}


# ---------------------------------------------------------------------------
# Generating a set for a domain
# ---------------------------------------------------------------------------
GEN_SYSTEM = """You write Stock and Flow Diagram (SFD) exercises for students of System
Dynamics, together with their answers. Each exercise is a short real-world scenario
in the given domain; the student reads it and draws the SFD.

Write the scenario in everyday language (90-160 words): describe what accumulates,
what increases and decreases it, and what those rates depend on, without naming
element types (do not say "stock", "flow", "auxiliary" in the scenario). End with
one sentence saying what to draw. The structure must match the level asked for.

The answer is a correct SFD. Element types:
- stock: an accumulation with state;
- flow: a rate that fills or drains a stock; it runs between stocks and/or clouds;
- auxiliary: a parameter, target, gap or computed rate constant;
- cloud: a source or sink at the model boundary (name each one distinctly);
- connector: an information link into a flow or an auxiliary.

Respond ONLY with JSON of exactly this shape:
{"title": "<short title>",
 "scenario": "<the scenario>",
 "expected_concepts": ["<4-6 teaching points, each naming an element and its TYPE>"],
 "solution": {"stocks": [{"label": ""}],
              "flows": [{"label": "", "from": "<stock or cloud>", "to": "<stock or cloud>"}],
              "auxiliaries": [{"label": ""}],
              "clouds": [{"label": ""}],
              "connectors": [{"from": "", "to": "<flow or auxiliary>"}]},
 "tutor_notes": "<what to accept as equivalent, what to insist on>"}
Every name used by a flow or connector must be declared, exactly as spelled.
Keep names short (1-3 words)."""


def _gen_user(domain: str, level: Tuple[str, str], taken: List[str], fix: str = "") -> str:
    out = (f"DOMAIN: {domain}\nLEVEL: {level[0]}\nSTRUCTURE REQUIRED: {level[1]}\n")
    if taken:
        out += "Already used in this set (pick a different situation): " + "; ".join(taken) + "\n"
    if fix:
        out += f"\nYour previous answer had these problems, fix them: {fix}\n"
    return out + "\nWrite the exercise now, as JSON only."


def generate_one(cfg: Dict, domain: str, level_index: int, taken: List[str],
                 complete_json=None) -> Tuple[Optional[Dict], Optional[str]]:
    """One exercise for one level, with its answer, checked; one retry."""
    complete_json = complete_json or llm_client.complete_json
    level = LEVELS[level_index]
    fix = ""
    for _ in range(2):
        data, err = complete_json(cfg, GEN_SYSTEM, _gen_user(domain, level, taken, fix),
                                  max_tokens=1800, timeout=90)
        if err:
            return None, err
        if not str(data.get("scenario", "")).strip():
            fix = "the scenario was missing"
            continue
        probs = check_solution(data.get("solution") or {})
        if probs:
            fix = "; ".join(probs[:4])
            continue
        n = level_index + 1
        return ({"id": f"gen{n}_{_slug(data.get('title', ''))}",
                 "type": "sfd",
                 "title": str(data.get("title") or "Exercise").strip(),   # numbered by the set
                 "difficulty": level[0],
                 "scenario": str(data["scenario"]).strip(),
                 "expected_concepts": [str(c) for c in data.get("expected_concepts") or []],
                 "solution": _clean_solution(data["solution"]),
                 "tutor_notes": str(data.get("tutor_notes") or "").strip()}, None)
    return None, f"the AI's answer for {level[0]} kept failing the checks ({fix})"


def random_domain(rng=random) -> str:
    return rng.choice(DOMAINS)
