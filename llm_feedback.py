"""
LLM feedback for submitted Stock and Flow Diagrams.

The API key is supplied by the USER at runtime, in the app's sidebar — just
like in CLD Tutor. It lives only in the browser session's memory
(st.session_state) and is sent directly to the provider chosen. No secrets
file is required (though one can optionally pre-fill the sidebar).

Provider-agnostic (Anthropic / OpenAI), implemented with the standard
library only — no SDK dependencies.

If no key is entered, the app falls back to a local heuristic review so the
prototype still runs and can be demoed offline.

The `llm_cfg` argument used throughout is either None (no key entered) or:

    {"provider": "anthropic"|"openai", "key": "<api key>", "model": "<model>"}
"""

import json
import textwrap
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
}


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


def _build_user_message(scenario, expected_concepts, diagram):
    concepts = "\n".join(f"- {c}" for c in expected_concepts)
    return textwrap.dedent(f"""
        SCENARIO
        {scenario}

        TEACHING POINTS (what a correct answer should capture)
        {concepts}

        STUDENT'S SUBMITTED DIAGRAM (JSON)
        {json.dumps(diagram, indent=2)}

        Grade this submission now.
    """).strip()


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
# Provider calls (standard library only)
# --------------------------------------------------------------------------
def _post(url, headers, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _err_msg(exc):
    """Human-readable message for an API/network failure."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            msg = (detail.get("error") or {}).get("message") or str(exc)
        except Exception:
            msg = str(exc)
        return f"API error ({exc.code}): {msg}"
    return f"Could not reach the LLM: {exc}"


def _call_llm(llm_cfg, system, user):
    """Send one system+user exchange to the configured provider."""
    provider = llm_cfg["provider"]
    api_key = llm_cfg["key"]
    model = (llm_cfg.get("model") or "").strip() or DEFAULT_MODELS[provider]

    if provider == "anthropic":
        data = _post(
            ANTHROPIC_URL,
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        return "".join(
            b.get("text", "") for b in data.get("content", [])
            if b.get("type") == "text"
        )

    # openai
    data = _post(
        OPENAI_URL,
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


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
        "summary": "Offline heuristic review (no API key entered).",
        "strengths": strengths or ["Diagram received."],
        "issues": issues or ["Add your API key in the sidebar for detailed, scenario-specific feedback."],
        "loops": (f"{len(stocks)} stock(s), {len(flows)} flow(s), "
                  f"{len(auxes)} auxiliary/auxiliaries detected."),
        "next_step": "Enter an LLM API key in the sidebar to get real tutoring feedback.",
    }


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------
def get_feedback(scenario, expected_concepts, diagram, llm_cfg):
    """
    Return structured feedback for a submitted SFD.

    Parameters
    ----------
    scenario : str
    expected_concepts : list[str]
    diagram : dict           the submitted SFD payload
                             ({"stocks", "flows", "auxiliaries", "clouds",
                               "connectors"})
    llm_cfg : dict or None   {"provider", "key", "model"} from the sidebar,
                             or None when no key has been entered

    Returns
    -------
    dict   parsed feedback (see SFD_SYSTEM_PROMPT for the shape)
    """
    if llm_cfg is None:
        return _heuristic_review(diagram)

    user = _build_user_message(scenario, expected_concepts, diagram)
    try:
        raw = _call_llm(llm_cfg, SFD_SYSTEM_PROMPT, user)
    except Exception as exc:  # network / auth / quota — degrade gracefully
        fb = _heuristic_review(diagram)
        fb["summary"] = f"{_err_msg(exc)} — showing offline review."
        return fb

    # The model is asked for bare JSON; strip stray fences just in case.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        return json.loads(raw)
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

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        sol = json.loads(raw)
    except json.JSONDecodeError:
        sol = _empty_solution()
        sol["_error"] = "The model's solution was not valid JSON."
        return sol

    for k, v in _empty_solution().items():
        sol.setdefault(k, v)
    return sol
