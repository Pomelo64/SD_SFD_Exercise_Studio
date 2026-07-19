# SFD Exercise Studio — Stock & Flow Diagram practice

A Streamlit app for learning the second core tool of System Dynamics: the
**Stock and Flow Diagram (SFD)**. Six exercises of gradually increasing
difficulty each present a written scenario; the student draws the SFD on an
interactive canvas with typed elements, and an AI tutor reviews the
submission — with a special eye on **type errors** (a stock drawn as an
auxiliary, a flow drawn as a connector) — and can also draw a model solution
to compare against.

Causal-loop practice lives in the companion app, **CLD Exercise Studio**.

## The API key comes from the user

Unlike a server-configured deployment, this app asks the **user** for their
LLM API key, in a hideable sidebar (the same pattern as *CLD Tutor*):

- pick a provider — **Anthropic (Claude)** or **OpenAI (ChatGPT)**;
- paste an API key (password field);
- optionally override the model name.

The key is kept only in the browser session's memory (`st.session_state`)
and is sent directly to the chosen provider from the server process handling
that session. **No secrets file is required.** Without a key, the app still
runs: submissions get a basic offline heuristic review, and the sidebar says
so. Each LLM review costs a fraction of a cent on the user's key.

(If you host the app and want the key field pre-filled for everyone, you can
optionally set `anthropic_api_key` / `openai_api_key` in Streamlit secrets —
see `.streamlit/secrets.toml.example`.)

## The six exercises — a difficulty ladder

| # | Exercise | Level | What it adds |
|---|---|---|---|
| 1 | The Bathtub | Warm-up | The minimal SFD: one stock, an inflow and an outflow, boundary clouds |
| 2 | The Coffee Cup | Basic | Auxiliaries + information **connectors** closing a feedback loop |
| 3 | Rabbit Population | Developing | Inflow **and** outflow on one stock; rate-constant auxiliaries |
| 4 | Room Thermostat | Intermediate | A goal-seeking control loop: setpoint, gap, connector-driven inflow |
| 5 | A Spreading Illness | Challenging | **Two stocks** and the first **stock-to-stock flow** (SIR-style epidemic) |
| 6 | Project Burnout | Advanced | Two stocks, four flows, multi-loop structure |

## What's in the box

```
SFD-Exercise-Studio/
├── app.py                 Main Streamlit app (landing page, sidebar key panel,
│                          exercise navigation, layout)
├── sfd_component/         The SFD drawing canvas (typed stock/flow editor)
│   ├── __init__.py
│   └── frontend/index.html
├── diagram_viewer/        Read-only viewer that renders the AI's solution
│   ├── __init__.py
│   └── frontend/index.html
├── llm_feedback.py        Provider-agnostic LLM calls (stdlib urllib only)
│                          + offline heuristic fallback
├── exercises/
│   └── exercises.json     The six scenarios + grading rubrics
├── requirements.txt       streamlit only — no SDK dependencies
├── .streamlit/secrets.toml.example   (optional key pre-fill; not required)
└── README.md
```

## The drawing canvas

A toolbar selects the active element type, each visually distinct:

| Element | Appearance | Role |
|---|---|---|
| Stock | blue rectangle | an accumulation |
| Flow | thick green pipe with a valve | a rate that fills/drains a stock |
| Auxiliary | amber circle | a converter / parameter |
| Cloud | grey dashed marker | a model boundary source or sink |
| Connector | thin grey arrow | an information link |

Place stocks/auxiliaries/clouds by clicking the canvas; draw flows and
connectors by clicking source then target. **No structural restrictions are
imposed** — students can connect anything to anything, and the LLM feedback
catches structural mistakes so errors become a teaching moment.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

That's it — no configuration. Open the sidebar in the app to add your API
key when you want AI feedback.

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. At https://share.streamlit.io, create a new app pointing at `app.py`.
3. Deploy. Users bring their own key via the sidebar; you don't pay for
   their LLM calls and hold no secrets.

## Adding exercises

Append an object to `exercises/exercises.json`:

```json
{
  "id": "sfd_unique_id",
  "type": "sfd",
  "title": "7 · Your Title",
  "difficulty": "Level 7 · …",
  "scenario": "The written scenario the student reads...",
  "expected_concepts": ["Teaching point 1", "Teaching point 2"]
}
```

`expected_concepts` is the rubric the LLM grades against — it is sent to the
model but never shown to the student. State the expected **type** of each
element (stock vs flow vs auxiliary), since type confusion is the main thing
the tutor checks.
