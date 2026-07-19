"""
SFD Exercise Studio — Stock and Flow Diagram practice.

Six exercises of gradually increasing difficulty. Each presents a written
scenario; the student draws the SFD on an interactive canvas and an AI tutor
reviews the submission.

The LLM API key is supplied by the USER in the sidebar (like in CLD Tutor):
pick Anthropic or OpenAI, paste a key, optionally set a model. The key lives
only in the browser session's memory and is sent directly to the provider.
Without a key, the app still runs with an offline heuristic review.

Run with:   streamlit run app.py
"""

import json
import os

import streamlit as st

from sfd_component import sfd_canvas
from diagram_viewer import diagram_viewer
from llm_feedback import DEFAULT_MODELS, get_feedback, get_solution

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="SFD Exercise Studio", page_icon="🛢️",
                   layout="wide")

_HERE = os.path.dirname(os.path.abspath(__file__))


@st.cache_data
def load_exercises():
    with open(os.path.join(_HERE, "exercises", "exercises.json")) as fh:
        return json.load(fh)


EXERCISES = load_exercises()


def get_secrets():
    """
    Return st.secrets as a plain dict, or {} if no secrets.toml exists.

    Secrets are OPTIONAL here — they are only used to pre-fill the sidebar's
    API-key field for convenience. Streamlit raises when no secrets file is
    present at all, so reading must be guarded.
    """
    try:
        return dict(st.secrets)
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Styling
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
      .stApp { background: #fbfaf7; }
      h1, h2, h3, h4 { font-family: Georgia, 'Times New Roman', serif; color: #1e293b; }
      .block-container { padding-top: 2.2rem; }
      .scenario-box {
        background: #fffdf8; border: 1px solid #d8d4cc; border-left: 4px solid #1e293b;
        padding: 16px 20px; border-radius: 3px; font-family: Georgia, serif;
        line-height: 1.6; color: #2b2b2b;
      }
      /* exercise-page variant: height matched to the canvas, scroll if longer */
      .scenario-box.fixed {
        height: 500px; overflow-y: auto; box-sizing: border-box;
      }
      .diff-tag {
        display: inline-block; font-size: 11px; letter-spacing: .08em;
        text-transform: uppercase; background: #1e293b; color: #fbfaf7;
        padding: 2px 9px; border-radius: 2px; font-family: Georgia, serif;
      }
      /* feedback column: card look, sticks near the top while you draw */
      .fb-card {
        background: #fffdf8; border: 1px solid #d8d4cc;
        border-radius: 4px; padding: 4px 18px 14px 18px;
      }
      /* landing page hero */
      .hero {
        text-align: center; padding: 30px 10px 10px 10px;
        font-family: Georgia, serif;
      }
      .hero .glyph { font-size: 58px; line-height: 1; color: #1e293b; }
      .hero h1 { font-size: 40px; margin: 12px 0 4px 0; }
      .hero .tag { color: #767067; font-style: italic; font-size: 16px; }
      .designer {
        text-align: center; margin-top: 26px; padding-top: 16px;
        border-top: 1px solid #d8d4cc; color: #767067;
        font-family: Georgia, serif; font-size: 14px;
      }
      .designer b { color: #1e293b; font-style: normal; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Navigation state
# --------------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "home"          # "home" or "exercises"
if "ex_index" not in st.session_state:
    st.session_state.ex_index = 0


def go_exercises():
    st.session_state.page = "exercises"


# --------------------------------------------------------------------------
# Sidebar — navigation, exercise picker, and the AI-tutor key panel
# --------------------------------------------------------------------------
def render_sidebar():
    """
    Draw the whole sidebar. Returns the LLM config dict
    {"provider", "key", "model"} when the user has entered an API key,
    else None (the app then falls back to the offline heuristic review).
    """
    secrets = get_secrets()

    with st.sidebar:
        st.markdown("## 🛢️ SFD Exercise Studio")
        st.caption("Practise System Dynamics by drawing stock & flow diagrams.")

        # ---- navigation + exercise picker (course page only) -------------
        if st.session_state.page == "exercises":
            st.button("← Home",
                      on_click=lambda: st.session_state.update(page="home"))
            st.divider()
            st.markdown("**Exercises**")

            titles = [ex["title"] for ex in EXERCISES]

            def _on_radio_change():
                st.session_state.ex_index = \
                    titles.index(st.session_state.ex_radio)

            # The radio is keyed; Next/Previous update ex_index, and we
            # mirror that into the radio's key so the two navigation paths
            # never disagree.
            st.session_state.ex_radio = titles[st.session_state.ex_index]
            st.radio(
                "Exercises", titles, key="ex_radio",
                captions=[ex["difficulty"] for ex in EXERCISES],
                label_visibility="collapsed", on_change=_on_radio_change,
            )

        st.divider()

        # ---- AI tutor key panel (same pattern as CLD Tutor) --------------
        st.markdown("## 🤖 AI tutor <small>(optional)</small>",
                    unsafe_allow_html=True)
        st.caption(
            "Add an API key to get **personalised tutor feedback** and an "
            "AI-drawn model solution for every exercise. Without a key, "
            "submissions get a basic offline review."
        )
        provider_label = st.selectbox(
            "Provider",
            ["Anthropic (Claude)", "OpenAI (ChatGPT)"],
            key="llm_provider_label",
        )
        provider = ("anthropic" if provider_label.startswith("Anthropic")
                    else "openai")

        # seed defaults once (avoids Streamlit's value-vs-key warning);
        # a secrets.toml can pre-fill the key but is entirely optional
        if "llm_api_key" not in st.session_state:
            st.session_state.llm_api_key = secrets.get(
                f"{provider}_api_key", "")
        if f"llm_model_{provider}" not in st.session_state:
            st.session_state[f"llm_model_{provider}"] = \
                DEFAULT_MODELS[provider]

        api_key = st.text_input(
            "API key",
            type="password",
            key="llm_api_key",
            placeholder="sk-ant-…" if provider == "anthropic" else "sk-…",
        )
        model = st.text_input(
            "Model",
            key=f"llm_model_{provider}",
            help="Leave the default unless you want a specific model.",
        )

        if api_key.strip():
            st.success(f"AI tutor **on** — {provider_label}", icon="✅")
        else:
            st.info("AI tutor **off** — offline heuristic review only.",
                    icon="💤")
        st.caption(
            "Your key is kept only in this browser session's memory and is "
            "sent directly to the provider you chose. Each review costs a "
            "fraction of a cent on your key."
        )

        st.divider()
        st.caption("Designed by **Shahin Ashkiani**")

    if api_key.strip():
        return {"provider": provider, "key": api_key.strip(), "model": model}
    return None


LLM_CFG = render_sidebar()


# ==========================================================================
# LANDING PAGE
# ==========================================================================
def render_landing():
    st.markdown(
        """
        <div class="hero">
          <div class="glyph">🛢️</div>
          <h1>SFD Exercise Studio</h1>
          <div class="tag">Stock &amp; Flow Diagram practice, from warm-up to advanced</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mid = st.columns([1, 2, 1])[1]
    with mid:
        st.markdown(
            """
            <div class="scenario-box">
            <b>What this app is for.</b><br><br>
            System Dynamics is a way of understanding how the parts of a system
            influence one another over time. Where Causal Loop Diagrams sketch
            influence, <i>Stock and Flow Diagrams</i> (SFDs) go a level deeper:
            they distinguish <i>stocks</i> (things that accumulate) from the
            <i>flows</i> that fill and drain them, with <i>auxiliaries</i>,
            boundary <i>clouds</i>, and information <i>connectors</i>
            completing the picture. Getting each element's <b>type</b> right
            is the core skill this app trains.
            <br><br>
            <b>How it works.</b><br><br>
            Each exercise gives you a short written scenario. Your task is to
            draw its SFD on an interactive canvas — place typed elements
            (stocks, flows, auxiliaries, clouds) and connect them. When you
            submit, an AI tutor reviews your diagram against the scenario and
            gives feedback — what you got right, what to fix, and the structure
            you should have found.
            <br><br>
            <b>Six exercises, rising difficulty.</b><br><br>
            The exercises are a ladder. You start with the simplest possible
            SFD (a bathtub: one stock, two flows), add connector-driven rates
            and feedback (a cooling coffee), combine inflow and outflow on one
            stock (a population), build a goal-seeking control loop (a
            thermostat), meet your first <i>stock-to-stock</i> flow (an
            epidemic), and finish with a two-stock, multi-loop burnout model.
            Work through them in order.
            <br><br>
            <b>Bring your own key.</b><br><br>
            To enable the AI tutor, open the sidebar and paste your own
            Anthropic (Claude) or OpenAI (ChatGPT) API key. The key stays in
            your browser session and goes only to the provider you choose.
            Without a key the app still works, with a basic offline review.
            <br><br>
            New to System Dynamics? The companion app, <i>CLD Exercise
            Studio</i>, covers Causal Loop Diagrams first.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        st.button("Start practising  →", type="primary",
                  use_container_width=True, on_click=go_exercises)

        st.markdown(
            '<div class="designer">Designed by <b>Shahin Ashkiani</b></div>',
            unsafe_allow_html=True,
        )


# ==========================================================================
# EXERCISE PAGE
# ==========================================================================
def render_feedback(feedback):
    """Render the tutor feedback in the bottom-left column."""
    st.markdown("#### Tutor feedback")
    score = feedback.get("score")
    if isinstance(score, (int, float)):
        st.progress(int(score) / 100, text=f"Score: {int(score)} / 100")
    if feedback.get("summary"):
        st.info(feedback["summary"])

    st.markdown("**What works**")
    for s in feedback.get("strengths", []) or ["—"]:
        st.markdown(f"- {s}")

    st.markdown("**What to fix**")
    for i in feedback.get("issues", []) or ["—"]:
        st.markdown(f"- {i}")

    if feedback.get("loops"):
        st.markdown(f"**Structure** — {feedback['loops']}")
    if feedback.get("next_step"):
        st.success(f"**Next step:** {feedback['next_step']}")


def render_exercises():
    idx = st.session_state.ex_index
    exercise = EXERCISES[idx]
    state_key = f"submitted_{exercise['id']}"

    def _has_content(d):
        """True if a submitted diagram has any elements."""
        return bool(d and (d.get("stocks") or d.get("flows")
                           or d.get("auxiliaries")))

    # ======================================================================
    # TOP ROW — exercise description (left)  |  drawing canvas (right)
    # ======================================================================
    scen_col, canvas_col = st.columns([1, 1.4], gap="large")

    with scen_col:
        st.markdown(f"### {exercise['title']}")
        st.markdown(f"<span class='diff-tag'>{exercise['difficulty']}</span>",
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(
            "<div class='scenario-box fixed'>"
            + exercise["scenario"].replace(chr(10), "<br><br>")
            + "</div>",
            unsafe_allow_html=True,
        )
        with st.expander("How to draw an SFD here"):
            st.markdown(
                "- **Pick a tool** in the toolbar: Stock, Auxiliary, "
                "Cloud, Flow, or Connector.\n"
                "- **Place an element** — with Stock/Auxiliary/Cloud "
                "active, click an empty spot on the canvas.\n"
                "- **Draw a flow** — with the Flow tool active, click the "
                "source element, then the target. A green pipe appears "
                "with a small **valve** (diamond) at its middle.\n"
                "- **Draw a connector** — with the Connector tool active, "
                "click the source, then the target. To feed a flow "
                "(e.g. an auxiliary driving a rate), click the flow's "
                "**valve** as the target.\n"
                "- **Element types** — Stock = blue rectangle, "
                "Auxiliary = amber circle, Cloud = grey boundary marker, "
                "Flow = green pipe with a valve, Connector = thin arrow.\n"
                "- **Rename** — double-click a stock, auxiliary, or valve. "
                "**Delete** — right-click any element (deleting a valve "
                "or pipe removes the whole flow).\n"
                "- Press **Submit diagram** to get tutor feedback.\n\n"
                "There are no restrictions — you can connect anything to "
                "anything. The tutor will point out structural mistakes."
            )

    with canvas_col:
        st.markdown("### Your diagram")

        # If this exercise was submitted before, hand the stored diagram back
        # to the canvas as its initial state so revisiting an exercise redraws
        # what the student submitted, instead of showing a blank canvas.
        prior = st.session_state.get(state_key)
        diagram = sfd_canvas(key=f"canvas_{exercise['id']}", initial=prior)

        # Only overwrite the stored submission with a *real* new submission.
        # A freshly-mounted canvas returns its default (None) or an empty
        # diagram on first render — neither should clobber a saved answer.
        if _has_content(diagram):
            st.session_state[state_key] = diagram

    # ======================================================================
    # BOTTOM ROW — tutor feedback (left)  |  AI's model solution (right)
    # ======================================================================
    st.write("")
    fb_left, sol_right = st.columns([1, 1], gap="large")
    submitted = st.session_state.get(state_key)

    # --- left: tutor feedback ---------------------------------------------
    with fb_left:
        st.markdown('<div class="fb-card">', unsafe_allow_html=True)
        if _has_content(submitted):
            with st.spinner("The tutor is reviewing your diagram…"):
                feedback = get_feedback(
                    scenario=exercise["scenario"],
                    expected_concepts=exercise["expected_concepts"],
                    diagram=submitted,
                    llm_cfg=LLM_CFG,
                )
            render_feedback(feedback)
        else:
            st.markdown("#### Tutor feedback")
            st.caption("Draw your SFD above, then press **Submit diagram**. "
                       "Your feedback will appear here.")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- right: the AI's model solution, revealed on its own button -------
    sol_key = f"solution_{exercise['id']}"
    with sol_right:
        st.markdown('<div class="fb-card">', unsafe_allow_html=True)
        st.markdown("#### AI's diagram")

        if not _has_content(submitted):
            st.caption("Submit your own diagram first. Then you can reveal a "
                       "model solution here to compare against.")
        elif LLM_CFG is None:
            st.caption("Generating a model solution needs an AI tutor — add "
                       "your API key in the sidebar to enable it.")
        else:
            if st.button("Show AI's SFD diagram",
                         key=f"showsol_{exercise['id']}"):
                with st.spinner("Generating a model SFD…"):
                    st.session_state[sol_key] = get_solution(
                        scenario=exercise["scenario"],
                        expected_concepts=exercise["expected_concepts"],
                        llm_cfg=LLM_CFG,
                    )

            solution = st.session_state.get(sol_key)
            if solution is None:
                st.caption("Press the button above to see how the AI would "
                           "draw this SFD, then compare it with your own.")
            elif solution.get("_error"):
                st.warning(solution["_error"])
            else:
                st.caption("A model solution — one valid answer, not the only "
                           "one. Drag the elements to tidy the layout; "
                           "compare it with your diagram above.")
                diagram_viewer(key=f"viewer_{exercise['id']}",
                               diagram=solution, kind="sfd")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- bottom navigation: previous / next -------------------------------
    st.divider()
    nav_prev, nav_mid, nav_next = st.columns([1, 2, 1])

    def go_prev():
        st.session_state.ex_index = max(0, st.session_state.ex_index - 1)

    def go_next():
        st.session_state.ex_index = min(len(EXERCISES) - 1,
                                        st.session_state.ex_index + 1)

    with nav_prev:
        st.button("← Previous exercise", disabled=(idx == 0),
                  use_container_width=True, on_click=go_prev)
    with nav_mid:
        st.markdown(
            f"<div style='text-align:center;color:#767067;"
            f"font-family:Georgia,serif;padding-top:6px'>"
            f"Exercise {idx + 1} of {len(EXERCISES)}</div>",
            unsafe_allow_html=True,
        )
    with nav_next:
        st.button("Next exercise →", type="primary",
                  disabled=(idx == len(EXERCISES) - 1),
                  use_container_width=True, on_click=go_next)


# ==========================================================================
# Router
# ==========================================================================
if st.session_state.page == "home":
    render_landing()
else:
    render_exercises()
