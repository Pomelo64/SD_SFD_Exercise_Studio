"""
LLM feedback for submitted Stock and Flow Diagrams.

The AI is a teaching assistant. When the exercise comes with an answer (a
lecturer's file, or a set generated with its answers), it grades against that
answer and the lecturer's notes, not against its own idea of the model. The
built-in exercises have only a rubric (expected_concepts); there the AI uses
the rubric and its own judgement, and can draw a model solution.

Calls go through llm_client (Claude, ChatGPT or Gemini; standard library only).
`llm_cfg` is {"provider": "anthropic"|"openai"|"gemini", "key": "...", "model": "..."}.
If the AI cannot be reached, a basic offline review is shown with the reason.
"""

import json
import re
import textwrap

import llm_client

DEFAULT_MODELS = llm_client.DEFAULT_MODELS


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------
SFD_SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert tutor in System Dynamics, grading a student's Stock and
    Flow Diagram (SFD). Be encouraging but precise.

    An SFD has TYPED elements, and getting the types right is the core skill:
      - STOCK: an accumulation that has state and persists over time
        (e.g. a population, an inventory, water in a tub).
      - FLOW: a RATE that fills or drains a stock. A flow connects a stock to
        another stock or to a CLOUD; it moves material.
      - AUXILIARY (converter): an intermediate variable or parameter, such as
        a rate constant, a target, or a computed gap.
      - CLOUD: a source or sink marking the model boundary — material that
        comes from or goes to outside the modelled system.
      - CONNECTOR: a thin information link. It carries INFORMATION (not
        material) into a flow or auxiliary, showing what that element depends
        on. A connector must NOT be used where a flow belongs.

    The most important things to check, in order:
      1. Are the right variables present, and is each given the CORRECT TYPE?
         The classic error is drawing a stock as an auxiliary (or a flow as a
         connector). Call these out explicitly.
      2. Do flows correctly connect stocks and clouds? Does every stock that
         should change have at least one flow attached?
      3. Are clouds used at the model boundary where appropriate?
      4. Do information connectors correctly show what each flow depends on?

    Be specific: name the element and say what type it should be instead.

    Respond ONLY with a JSON object, no markdown fences, of the form:
    {
      "score": <integer 0-100>,
      "summary": "<one-sentence overall verdict>",
      "strengths": ["<short bullet>", ...],
      "issues": ["<short bullet, naming the element and its correct type>", ...],
      "loops": "<short note on the stock/flow structure the student should have>",
      "next_step": "<one concrete suggestion>"
    }
""").strip()

SFD_SOLUTION_PROMPT = textwrap.dedent("""
    You are an expert in System Dynamics. Given a scenario, produce a correct
    Stock and Flow Diagram (SFD) for it.

    Element types:
      - stock: an accumulation that has state.
      - flow: a rate that fills or drains a stock; it connects a stock to
        another stock or to a cloud.
      - auxiliary: an intermediate variable, rate constant, target, or gap.
      - cloud: a source or sink marking the model boundary.
      - connector: a thin information link feeding a flow or auxiliary.

    Respond ONLY with a JSON object, no markdown fences, of EXACTLY this shape:
    {
      "stocks":      [{"label": "<name>"}, ...],
      "flows":       [{"label": "<name>", "from": "<stock or cloud label>",
                       "to": "<stock or cloud label>"}, ...],
      "auxiliaries": [{"label": "<name>"}, ...],
      "clouds":      [{"label": "<name>"}, ...],
      "connectors":  [{"from": "<source label>", "to": "<target label>"}, ...]
    }
    Every label referenced by a flow or connector MUST match a declared
    element label exactly. Name clouds distinctly (e.g. "source", "sink").
    Keep labels short. Include only what the scenario justifies.
""").strip()


def _build_user_message(scenario, expected_concepts, diagram, solution=None,
                        tutor_notes="", answer_from="the lecturer"):
    concepts = "\n".join(f"- {c}" for c in expected_concepts) or "- (none given)"
    ref = ""
    if solution:
        ref = textwrap.dedent(f"""

            REFERENCE ANSWER (from {answer_from}; authoritative)
            {json.dumps(solution, indent=2)}
        """)
    notes = f"\n\nNOTES FOR THE TUTOR (from {answer_from})\n{tutor_notes}" if tutor_notes else ""
    how = ("Grade against the REFERENCE ANSWER and the notes: they are what this course "
           "expects. Names need not match exactly; judge the structure and each element's "
           "type. If the student's diagram is a sound alternative the reference does not "
           "cover, say so, and explain how it differs from what the course expects. Never "
           "contradict the reference answer."
           if solution else
           "Grade against the teaching points and your own judgement.")
    return (f"SCENARIO\n{scenario}\n\nTEACHING POINTS (what a correct answer should "
            f"capture)\n{concepts}{ref}{notes}\n\nSTUDENT'S SUBMITTED DIAGRAM (JSON)\n"
            f"{json.dumps(diagram, indent=2)}\n\n{how}\nGrade this submission now.")


def _build_solution_message(scenario, expected_concepts):
    concepts = "\n".join(f"- {c}" for c in expected_concepts)
    return textwrap.dedent(f"""
        SCENARIO
        {scenario}

        KEY POINTS the diagram should capture
        {concepts}

        Produce the diagram now, as JSON only.
    """).strip()


# --------------------------------------------------------------------------
# Provider calls: the shared client
# --------------------------------------------------------------------------
def _call_llm(llm_cfg, system, user, max_tokens=1400):
    text, err = llm_client.complete(llm_cfg, system, user, max_tokens=max_tokens,
                                    want_json=True, timeout=60)
    if err:
        raise RuntimeError(err)
    return text


def _err_msg(exc):
    return str(exc)


# --------------------------------------------------------------------------
# Offline fallback (keeps the app usable without an API key)
# --------------------------------------------------------------------------
def _heuristic_review(diagram):
    stocks = diagram.get("stocks", [])
    flows = diagram.get("flows", [])
    auxes = diagram.get("auxiliaries", [])
    clouds = diagram.get("clouds", [])
    conns = diagram.get("connectors", [])
    issues, strengths = [], []

    if not stocks:
        issues.append("No stock drawn — every SFD needs at least one accumulation.")
    else:
        strengths.append(f"You defined {len(stocks)} stock(s).")
    if not flows:
        issues.append("No flows drawn — a stock can only change through flows.")
    else:
        strengths.append(f"You drew {len(flows)} flow(s).")
        dangling = sum(1 for f in flows if not f.get("from") or not f.get("to"))
        if dangling:
            issues.append(f"{dangling} flow(s) have an unattached end — "
                          "connect each flow to a stock or a cloud.")
    if auxes:
        strengths.append(f"You added {len(auxes)} auxiliary/auxiliaries.")
    if clouds:
        strengths.append(f"You marked {len(clouds)} boundary cloud(s).")
    if conns:
        strengths.append(f"You drew {len(conns)} information connector(s).")

    total = len(stocks) + len(flows) + len(auxes) + len(conns)
    score = min(100, 18 * len(stocks) + 14 * len(flows)
                + 6 * len(auxes) + 5 * len(conns)) if total else 10
    return {
        "score": score,
        "summary": "Offline review (basic counts only).",
        "strengths": strengths or ["Diagram received."],
        "issues": issues or ["The AI tutor could not review this one; try submitting again."],
        "loops": (f"{len(stocks)} stock(s), {len(flows)} flow(s), "
                  f"{len(auxes)} auxiliary/auxiliaries detected."),
        "next_step": "Submit again when the AI can be reached, for scenario-specific feedback.",
    }


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------
def get_feedback(scenario, expected_concepts, diagram, llm_cfg, solution=None,
                 tutor_notes="", answer_from="the lecturer"):
    """
    Structured feedback for a submitted SFD (see SFD_SYSTEM_PROMPT for the
    shape). With a `solution` (the exercise's answer), the tutor grades against
    it and the `tutor_notes`.
    """
    if llm_cfg is None:
        return _heuristic_review(diagram)
    user = _build_user_message(scenario, expected_concepts, diagram, solution,
                               tutor_notes, answer_from)
    try:
        raw = _call_llm(llm_cfg, SFD_SYSTEM_PROMPT, user)
    except Exception as exc:  # network / auth / quota — degrade gracefully
        fb = _heuristic_review(diagram)
        fb["summary"] = f"{_err_msg(exc)} — showing the offline review."
        return fb
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0) if m else raw)
    except json.JSONDecodeError:
        return {
            "score": None,
            "summary": "The tutor replied, but not in the expected format.",
            "strengths": [],
            "issues": ["Could not parse structured feedback."],
            "loops": "",
            "next_step": raw[:600],
        }


def _empty_solution():
    return {"stocks": [], "flows": [], "auxiliaries": [],
            "clouds": [], "connectors": []}


def get_solution(scenario, expected_concepts, llm_cfg):
    """
    Ask the LLM to produce a correct SFD for the scenario.

    Returns a diagram in the same schema the canvas uses, plus an "_error"
    key (str) if the solution could not be generated.
    """
    if llm_cfg is None:
        sol = _empty_solution()
        sol["_error"] = ("No API key entered — generating a model solution "
                         "needs a key in the sidebar.")
        return sol

    user = _build_solution_message(scenario, expected_concepts)
    try:
        raw = _call_llm(llm_cfg, SFD_SOLUTION_PROMPT, user)
    except Exception as exc:
        sol = _empty_solution()
        sol["_error"] = _err_msg(exc)
        return sol

    m = re.search(r"\{.*\}", raw, re.S)
    try:
        sol = json.loads(m.group(0) if m else raw)
    except json.JSONDecodeError:
        sol = _empty_solution()
        sol["_error"] = "The model's solution was not valid JSON."
        return sol

    for k, v in _empty_solution().items():
        sol.setdefault(k, v)
    return sol
