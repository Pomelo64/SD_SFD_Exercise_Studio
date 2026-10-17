"""
SFD Exercise Studio — Stock and Flow Diagram practice.

The app starts like Causal Loop Colab: first an AI key (Claude, ChatGPT or
Gemini), tested before anything else opens. Then the student chooses where
the exercises come from:

  🎲 the app picks a domain and writes a set of exercises, with answers;
  📚 the built-in ladder of six exercises (the same for everyone);
  📥 a set from the lecturer (a JSON file with the exercises and answers) —
     the AI then works as a teaching assistant, grading against the answers;
  ✍️ the student names a domain and the app writes the exercises, with answers.

Each exercise: read the scenario, draw the SFD, submit, get feedback; then
compare with the answer.

Run with:   streamlit run app.py
"""

import hashlib
import json

import streamlit as st

import exercise_sets as XS
import llm_client
from diagram_viewer import diagram_viewer
from llm_feedback import get_feedback, get_solution
from sfd_component import sfd_canvas

st.set_page_config(page_title="SFD Exercise Studio", page_icon="🛢️", layout="wide")
ss = st.session_state


def get_secrets():
    try:
        return dict(st.secrets)
    except Exception:
        return {}


def secrets_cfg():
    """A key set for this deployment (optional), used only after a test."""
    sec = get_secrets()
    prov = str(sec.get("llm_provider") or "").strip().lower()
    if not prov:
        prov = next((p for p in llm_client.PROVIDERS if sec.get(f"{p}_api_key")), "")
    key = str(sec.get(f"{prov}_api_key") or "").strip() if prov else ""
    if prov in llm_client.PROVIDERS and key:
        return {"provider": prov, "key": key,
                "model": str(sec.get("llm_model") or llm_client.DEFAULT_MODELS[prov])}
    return None


# --------------------------------------------------------------------------
# Styling: no fixed text or page colours, so light and dark themes both read
# --------------------------------------------------------------------------
st.markdown("""
<style>
  h1, h2, h3, h4 { font-family: Georgia, 'Times New Roman', serif; }
  .block-container { padding-top: 2.2rem; }
  .scenario-box {
    background: rgba(128,128,128,.06); border: 1px solid rgba(128,128,128,.3);
    border-left: 4px solid currentColor; padding: 16px 20px; border-radius: 3px;
    font-family: Georgia, serif; line-height: 1.6;
  }
  .scenario-box.fixed { height: 500px; overflow-y: auto; box-sizing: border-box; }
  .diff-tag {
    display: inline-block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
    border: 1px solid currentColor; padding: 2px 9px; border-radius: 2px;
    font-family: Georgia, serif; opacity: .85;
  }
  .hero { text-align: center; padding: 26px 10px 6px 10px; font-family: Georgia, serif; }
  .hero .glyph { font-size: 54px; line-height: 1; }
  .hero h1 { font-size: 40px; margin: 12px 0 4px 0; }
  .hero .tag { opacity: .72; font-style: italic; font-size: 16px; }
  .step { font-family: Georgia, serif; font-size: 13px; letter-spacing: .08em;
          text-transform: uppercase; opacity: .7; margin-bottom: -6px; }
  .designer { text-align: center; margin-top: 26px; padding-top: 16px; opacity: .75;
              border-top: 1px solid rgba(128,128,128,.3); font-family: Georgia, serif;
              font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
ss.setdefault("page", "home")          # "home" (key + choice of exercises) or "exercises"
ss.setdefault("ex_index", 0)
ss.setdefault("cfg", None)             # the tested AI settings
ss.setdefault("ex_set", None)          # the chosen exercise set
ss.setdefault("set_uid", 0)            # changes with every new set (keys stay unique)

SOURCE_LABEL = {
    "default": "📚 Built-in exercises",
    "generated-random": "🎲 Written by the AI for a domain it picked",
    "generated-domain": "✍️ Written by the AI for your domain",
    "imported": "📥 From your lecturer",
}


def start_set(ex_set):
    ss.ex_set = ex_set
    ss.set_uid += 1
    ss.ex_index = 0
    ss.page = "exercises"


# ==========================================================================
# STEP 1 — the AI key (the app does not open without one)
# ==========================================================================
def key_card():
    st.markdown("<div class='step'>Step 1 of 2</div>", unsafe_allow_html=True)
    st.markdown("### 🔑 Connect an AI")
    st.caption("The AI writes exercises, reviews your diagrams and works as your teaching "
               "assistant. Paste a key from one provider and test it. The key stays in this "
               "browser session's memory and is sent only to that provider.")
    labels = list(llm_client.PROVIDERS.values())
    label = st.selectbox("Provider", labels, key="k_prov")
    provider = next(k for k, v in llm_client.PROVIDERS.items() if v == label)
    key = st.text_input("API key", type="password", key=f"k_key_{provider}",
                        placeholder=llm_client.KEY_PLACEHOLDER[provider])
    if f"k_model_{provider}" not in ss:
        ss[f"k_model_{provider}"] = llm_client.DEFAULT_MODELS[provider]
    model = st.text_input("Model", key=f"k_model_{provider}",
                          help="Leave the default unless you want a specific model.")
    fallback = secrets_cfg()
    c1, c2 = st.columns(2)
    test = c1.button("Test the key and continue", type="primary", use_container_width=True)
    use_app = fallback is not None and c2.button(
        "Use the key set for this app", use_container_width=True,
        help="This deployment has its own key; it is tested, never shown.")
    cfg = None
    if test:
        if not key.strip():
            st.warning("Paste a key first.")
        else:
            cfg = {"provider": provider, "key": key.strip(), "model": model.strip()}
    elif use_app and fallback:
        cfg = fallback
    if cfg:
        with st.spinner("Asking the AI to say hello…"):
            ok, err = llm_client.test_connection(cfg)
        if ok:
            ss.cfg = cfg
            st.rerun()
        st.error(err)


# ==========================================================================
# STEP 2 — where the exercises come from
# ==========================================================================
def generate_set(domain, levels, source):
    exs, problems = [], []
    bar = st.progress(0.0, text=f"Writing exercises about {domain}…")
    for n, li in enumerate(levels):
        bar.progress(n / len(levels),
                     text=f"Writing exercise {n + 1} of {len(levels)} ({XS.LEVELS[li][0]})…")
        ex, err = XS.generate_one(ss.cfg, domain, li, [e["title"] for e in exs])
        if ex:
            exs.append(ex)
        else:
            problems.append(f"{XS.LEVELS[li][0]}: {err}")
            if "API error" in str(err) or "reach" in str(err).lower():
                break                              # the AI is down: stop asking
    bar.empty()
    if not exs:
        st.error("No exercises could be written. " + " ".join(problems[:2]))
        return
    for i, ex in enumerate(exs, 1):                  # number them in the set's order
        ex["title"] = f"{i} · {ex['title']}"
    title = f"Exercises: {domain}"
    ex_set = {"format": XS.FORMAT, "version": 1, "title": title, "domain": domain,
              "author": f"AI ({llm_client.PROVIDERS[ss.cfg['provider']]} · {ss.cfg['model']})",
              "source": source, "reveal_answers": "after_submit", "exercises": exs}
    ss.gen_problems = problems
    start_set(ex_set)
    st.rerun()


def source_card():
    st.markdown("<div class='step'>Step 2 of 2</div>", unsafe_allow_html=True)
    st.markdown("### 📚 Choose your exercises")
    opts = ["🎲 Let the app choose a domain",
            "📚 The built-in exercises",
            "📥 Import exercises from your lecturer",
            "✍️ Choose your own domain"]
    pick = st.radio("Where should the exercises come from?", opts, key="src_pick",
                    captions=["The app picks a domain at random and writes exercises "
                              "with their answers.",
                              "Six generic exercises from warm-up to advanced — the same "
                              "for everyone, so the experience is reproducible.",
                              "A .json file with exercises and answers. The AI acts as a "
                              "teaching assistant and grades against your lecturer's answers.",
                              "Name a domain; the app writes exercises with their answers."],
                    label_visibility="collapsed")
    st.write("")
    sizes = {"3 exercises (quicker)": XS.QUICK, "6 exercises (the full ladder)": list(range(6))}

    if pick == opts[0]:
        n = st.radio("How many?", list(sizes), horizontal=True, key="n_random")
        if st.button("Pick a domain and write the exercises", type="primary"):
            generate_set(XS.random_domain(), sizes[n], "generated-random")
    elif pick == opts[1]:
        if st.button("Start the built-in exercises", type="primary"):
            start_set(XS.load_default())
            st.rerun()
    elif pick == opts[2]:
        up = st.file_uploader("Your lecturer's exercise file (.json)", type=["json"],
                              key="imp_file")
        st.download_button("Lecturers: download a template (.json)",
                           json.dumps(XS.TEMPLATE, indent=2, ensure_ascii=False),
                           file_name="sfd_exercises_template.json", mime="application/json",
                           help="One exercise with every field filled in. See the README.")
        if up is not None:
            try:
                data = json.loads(up.getvalue().decode("utf-8"))
            except Exception as exc:
                st.error(f"That file is not valid JSON: {exc}")
                return
            ex_set, errors, warns = XS.normalise(data, "imported")
            for e in errors:
                st.error(e)
            for w in warns:
                st.warning(w)
            if ex_set:
                n_ans = sum(1 for e in ex_set["exercises"] if e.get("solution"))
                st.success(f"**{ex_set['title']}** — {len(ex_set['exercises'])} exercises, "
                           f"{n_ans} with an answer diagram"
                           + (f" · by {ex_set['author']}" if ex_set.get("author") else ""))
                if st.button("Start these exercises", type="primary"):
                    start_set(ex_set)
                    st.rerun()
    else:
        dom = st.text_input("Your domain", key="own_domain",
                            placeholder="e.g. tourism in a mountain village, a school's "
                                        "canteen, antibiotic resistance")
        n = st.radio("How many?", list(sizes), horizontal=True, key="n_domain")
        if st.button("Write the exercises", type="primary"):
            if len(dom.strip()) < 3:
                st.warning("Name a domain first.")
            else:
                generate_set(dom.strip()[:120], sizes[n], "generated-domain")


def render_home():
    st.markdown("""
    <div class="hero"><div class="glyph">🛢️</div><h1>SFD Exercise Studio</h1>
    <div class="tag">Stock &amp; Flow Diagram practice, with an AI teaching assistant</div></div>
    """, unsafe_allow_html=True)
    mid = st.columns([1, 2, 1])[1]
    with mid:
        with st.expander("What this app is for"):
            st.markdown(
                "Stock and Flow Diagrams (SFDs) distinguish **stocks** (things that "
                "accumulate) from the **flows** that fill and drain them, with "
                "**auxiliaries**, boundary **clouds** and information **connectors** "
                "completing the picture. Getting each element's **type** right is the core "
                "skill this app trains.\n\n"
                "Each exercise gives a short scenario. Draw its SFD on the canvas and "
                "submit: the AI tutor tells you what works, what to fix, and how your "
                "diagram compares with the expected structure. Then you can reveal the "
                "answer to compare.\n\n"
                "New to System Dynamics? Start with Causal Loop Diagrams in the companion "
                "app, *CLD Exercise Studio*.")
        with st.container(border=True):
            if ss.cfg is None:
                key_card()
            else:
                st.caption(f"✅ AI connected — {llm_client.PROVIDERS[ss.cfg['provider']]} · "
                           f"{ss.cfg['model']}")
                source_card()
        st.markdown('<div class="designer">Designed by <b>Shahin Ashkiani</b></div>',
                    unsafe_allow_html=True)


# ==========================================================================
# Sidebar
# ==========================================================================
def render_sidebar():
    with st.sidebar:
        st.markdown("## 🛢️ SFD Exercise Studio")
        if ss.page == "exercises" and ss.ex_set:
            xs = ss.ex_set
            st.markdown(f"**{xs['title']}**")
            st.caption(SOURCE_LABEL.get(xs.get("source"), "")
                       + (f" · by {xs['author']}" if xs.get("author") else ""))
            if st.button("← Choose other exercises", use_container_width=True):
                ss.page = "home"
                st.rerun()
            st.divider()
            titles = [ex["title"] for ex in xs["exercises"]]
            ss.ex_radio_i = min(ss.ex_index, len(titles) - 1)
            st.radio("Exercises", list(range(len(titles))), key="ex_radio_i",
                     format_func=lambda i: titles[i],
                     captions=[ex.get("difficulty", "") for ex in xs["exercises"]],
                     label_visibility="collapsed",
                     on_change=lambda: ss.update(ex_index=ss.ex_radio_i))
            st.download_button(
                "⬇ Download this exercise set (.json)", XS.export(xs),
                file_name=f"sfd_exercises_{XS._slug(xs.get('domain') or xs['title'])}.json",
                mime="application/json", use_container_width=True,
                help="Lecturers: review or edit it, then share it with students, who open it "
                     "with “Import exercises from your lecturer”.")
            st.divider()
        if ss.cfg:
            st.caption(f"🤖 AI: {llm_client.PROVIDERS[ss.cfg['provider']]} · {ss.cfg['model']}")
            if st.button("Change the AI key", use_container_width=True):
                ss.cfg = None
                ss.page = "home"
                st.rerun()
        st.caption("Your key stays in this browser session's memory and goes only to the "
                   "provider you chose.")
        st.divider()
        st.caption("Designed by **Shahin Ashkiani**")


# ==========================================================================
# EXERCISE PAGE
# ==========================================================================
def render_feedback(feedback):
    st.markdown("#### Tutor feedback")
    score = feedback.get("score")
    if isinstance(score, (int, float)):
        st.progress(max(0, min(100, int(score))) / 100, text=f"Score: {int(score)} / 100")
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


def _has_content(d):
    return bool(d and (d.get("stocks") or d.get("flows") or d.get("auxiliaries")))


def render_exercises():
    xs = ss.ex_set
    exs = xs["exercises"]
    idx = min(ss.ex_index, len(exs) - 1)
    exercise = exs[idx]
    uid = f"{ss.set_uid}_{exercise['id']}"
    state_key = f"submitted_{uid}"
    source = xs.get("source", "default")

    for p in ss.pop("gen_problems", []) or []:
        st.warning(f"One exercise could not be written: {p}")

    scen_col, canvas_col = st.columns([1, 1.4], gap="large")
    with scen_col:
        st.markdown(f"### {exercise['title']}")
        if exercise.get("difficulty"):
            st.markdown(f"<span class='diff-tag'>{exercise['difficulty']}</span>",
                        unsafe_allow_html=True)
        st.write("")
        import html as _html
        st.markdown("<div class='scenario-box fixed'>"
                    + _html.escape(exercise["scenario"]).replace(chr(10), "<br><br>")
                    + "</div>", unsafe_allow_html=True)
        with st.expander("How to draw an SFD here"):
            st.markdown(
                "- **Pick a tool** in the toolbar: Stock, Auxiliary, Cloud, Flow, or Connector.\n"
                "- **Place an element** — with Stock/Auxiliary/Cloud active, click an empty "
                "spot on the canvas.\n"
                "- **Draw a flow** — with the Flow tool, click the source, then the target. "
                "A green pipe appears with a small **valve** (diamond) at its middle.\n"
                "- **Draw a connector** — with the Connector tool, click the source, then the "
                "target. To feed a flow, click the flow's **valve** as the target.\n"
                "- **Rename** — double-click a stock, auxiliary, or valve. **Delete** — "
                "right-click any element.\n"
                "- Press **Submit diagram** to get tutor feedback.")

    with canvas_col:
        st.markdown("### Your diagram")
        prior = ss.get(state_key)
        diagram = sfd_canvas(key=f"canvas_{uid}", initial=prior)
        if _has_content(diagram):
            ss[state_key] = diagram

    st.write("")
    fb_left, sol_right = st.columns([1, 1], gap="large")
    submitted = ss.get(state_key)
    answer_from = ("your lecturer" if source == "imported" else
                   "the exercise set (written with the exercise)")

    # --- left: feedback, once per submission (not on every rerun) -----------
    with fb_left:
        with st.container(border=True):
            if _has_content(submitted):
                sig = hashlib.md5(json.dumps(submitted, sort_keys=True).encode()).hexdigest()
                cached = ss.get(f"fb_{uid}")
                if not cached or cached[0] != sig:
                    with st.spinner("The tutor is reviewing your diagram…"):
                        fb = get_feedback(
                            scenario=exercise["scenario"],
                            expected_concepts=exercise.get("expected_concepts", []),
                            diagram=submitted, llm_cfg=ss.cfg,
                            solution=exercise.get("solution"),
                            tutor_notes=exercise.get("tutor_notes", ""),
                            answer_from=answer_from)
                    ss[f"fb_{uid}"] = (sig, fb)
                render_feedback(ss[f"fb_{uid}"][1])
                if exercise.get("solution"):
                    st.caption(f"Graded against the answer from {answer_from}.")
            else:
                st.markdown("#### Tutor feedback")
                st.caption("Draw your SFD above, then press **Submit diagram**. Your feedback "
                           "will appear here.")

    # --- right: the answer --------------------------------------------------
    sol_key = f"solution_{uid}"
    with sol_right:
        with st.container(border=True):
            st.markdown("#### The answer")
            sol = exercise.get("solution")
            if sol and xs.get("reveal_answers") == "never":
                st.caption("Your lecturer has chosen not to show the answer here. The tutor's "
                           "feedback is based on it.")
            elif not _has_content(submitted):
                st.caption("Submit your own diagram first. Then you can reveal the answer to "
                           "compare.")
            elif sol:
                if st.button("Show the answer", key=f"showsol_{uid}"):
                    ss[sol_key] = sol
                if ss.get(sol_key):
                    st.caption(("Your lecturer's answer." if source == "imported" else
                                "The answer written with this exercise.")
                               + " Drag the elements to tidy the layout.")
                    diagram_viewer(key=f"viewer_{uid}", diagram=ss[sol_key], kind="sfd")
            else:
                if st.button("Show the AI's SFD", key=f"showsol_{uid}"):
                    with st.spinner("Drawing a model SFD…"):
                        ss[sol_key] = get_solution(
                            scenario=exercise["scenario"],
                            expected_concepts=exercise.get("expected_concepts", []),
                            llm_cfg=ss.cfg)
                solution = ss.get(sol_key)
                if solution is None:
                    st.caption("This exercise has no stored answer: the AI draws one valid "
                               "solution for you to compare with.")
                elif solution.get("_error"):
                    st.warning(solution["_error"])
                else:
                    st.caption("A model solution — one valid answer, not the only one.")
                    diagram_viewer(key=f"viewer_{uid}", diagram=solution, kind="sfd")

    st.divider()
    nav_prev, nav_mid, nav_next = st.columns([1, 2, 1])
    nav_prev.button("← Previous exercise", disabled=(idx == 0), use_container_width=True,
                    on_click=lambda: ss.update(ex_index=max(0, idx - 1)))
    nav_mid.markdown(f"<div style='text-align:center;opacity:.7;font-family:Georgia,serif;"
                     f"padding-top:6px'>Exercise {idx + 1} of {len(exs)}</div>",
                     unsafe_allow_html=True)
    nav_next.button("Next exercise →", type="primary", disabled=(idx == len(exs) - 1),
                    use_container_width=True,
                    on_click=lambda: ss.update(ex_index=min(len(exs) - 1, idx + 1)))


# ==========================================================================
# Router: no AI key, no exercises
# ==========================================================================
render_sidebar()
if ss.cfg is None or ss.page == "home" or not ss.ex_set:
    render_home()
else:
    render_exercises()
