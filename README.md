# SFD Exercise Studio — Stock & Flow Diagram practice

A Streamlit app for learning the second core tool of System Dynamics: the
**Stock and Flow Diagram (SFD)**. Each exercise presents a written scenario;
the student draws the SFD on an interactive canvas with typed elements, and an
AI tutor reviews the submission — with a special eye on **type errors** (a
stock drawn as an auxiliary, a flow drawn as a connector). The exercises can be
the built-in ladder of six, a set the AI writes for a domain (chosen by the
student or picked at random), or a set from a lecturer, with answers the AI
grades against.

Causal-loop practice lives in the companion app, **CLD Exercise Studio**.

## Starting: an AI key, then a choice of exercises

Like *Causal Loop Colab*, the app opens with **Step 1 — Connect an AI**: pick
**Anthropic (Claude)**, **OpenAI (ChatGPT)** or **Google (Gemini)**, paste a key,
and press **Test the key and continue**. Nothing else opens until the key works.
The key stays in the browser session's memory and goes only to that provider. A
deployment can also set its own key in Streamlit secrets; the app then offers
**Use the key set for this app** (the key is tested, never shown — see
`.streamlit/secrets.toml.example`).

**Step 2 — Choose your exercises**, from four sources:

| | Source | What happens |
|---|---|---|
| 🎲 | **Let the app choose a domain** | The app picks a domain at random (a coral reef, a hospital emergency department, a city's bike-sharing scheme…) and the AI writes the exercises with their answers. |
| 📚 | **The built-in exercises** | The six generic exercises below — the same for everyone, so the experience is reproducible. |
| 📥 | **Import exercises from your lecturer** | A `.json` file with the exercises **and their answers**. The AI works as a teaching assistant: it grades against the lecturer's answers and notes, not its own idea of the model. |
| ✍️ | **Choose your own domain** | The student names a domain; the AI writes the exercises with their answers. |

Generated sets have **3 exercises** (levels 1, 3 and 5 — quicker) or **6** (the full
ladder). Each exercise is written for one level of the ladder below, with a
scenario, teaching points, an **answer diagram** and notes for the tutor. Every
answer is checked before it is used (each flow runs between declared stocks or
clouds, every stock has a flow, every connector names a real element); an answer
that fails is sent back to the AI once with the problems listed.

**From then on, all sources work the same way:** read the scenario, draw the SFD,
submit, get feedback. Feedback is written once per submission (the earlier
version asked the AI again on every page refresh). After submitting, **Show the
answer** reveals the set's answer diagram; for the built-in exercises, which have
no stored answer, the AI draws one.

## For lecturers: making an exercise set

1. Generate a set with 🎲 or ✍️, or start from the template (**Lecturers: download
   a template** under 📥).
2. **Download this exercise set (.json)** from the sidebar, then review and edit it:
   rewrite scenarios, correct answers, add your notes.
3. Share the file. Students open it with **Import exercises from your lecturer**.

The format (`bluejay-sfd-exercises`, version 1):

```json
{
  "format": "bluejay-sfd-exercises", "version": 1,
  "title": "Water and cities", "domain": "urban water", "author": "Dr …",
  "reveal_answers": "after_submit",
  "exercises": [{
    "id": "bathtub", "title": "1 · The Bathtub", "difficulty": "Level 1 · Warm-up",
    "scenario": "The text students read…",
    "expected_concepts": ["The STOCK is the water in the tub.", "…"],
    "solution": {
      "stocks": [{"label": "Water in tub"}],
      "flows": [{"label": "filling", "from": "tap", "to": "Water in tub"},
                {"label": "draining", "from": "Water in tub", "to": "drain"}],
      "auxiliaries": [], "clouds": [{"label": "tap"}, {"label": "drain"}],
      "connectors": []},
    "tutor_notes": "Accept any name for the stock. Insist the water is a stock."
  }]
}
```

- `scenario` is required; `expected_concepts` (the rubric), `solution` (the answer
  diagram) and `tutor_notes` are optional but make the tutor follow your intent.
  Name each element's **type** in the rubric — type confusion is what the tutor
  checks most.
- A flow runs `from` and `to` a stock or a cloud; a connector runs `from` any
  element `to` a flow or auxiliary; names must match exactly.
- `"reveal_answers": "never"` keeps the answer diagram hidden in the app (the tutor
  still grades against it).
- The importer explains any problem: an exercise without a scenario is skipped; an
  answer diagram that doesn't hold together is left out, with a warning, and the
  rubric is used instead.
- A bare list of exercises (like `exercises/exercises.json`) is accepted too.

**Be aware:** the answers travel inside the file the students import, so a student
who opens the file can read them. The app has no server of its own to keep them
secret; treat the set as practice material, not as an exam.

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
├── llm_feedback.py        Tutor feedback (graded against the set's answer when there
│                          is one) and model solutions; offline fallback
├── llm_client.py          Claude / ChatGPT / Gemini client (standard library only)
├── exercise_sets.py       Exercise sets: format, checks, import, export, generation
├── exercises/
│   └── exercises.json     The six scenarios + grading rubrics
├── requirements.txt       streamlit only — no SDK dependencies
├── .streamlit/config.toml           light-theme colours (dark theme works too)
├── .streamlit/secrets.toml.example   (optional deployment key; not required)
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

No configuration: the app asks for an AI key when it opens.

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. At https://share.streamlit.io, create a new app pointing at `app.py`.
3. Deploy. Users bring their own key; you don't pay for their AI calls and hold
   no secrets. (Optionally, set a key in **App → Settings → Secrets** for a
   "Use the key set for this app" button.)

## Adding exercises to the built-in set

Append an object to `exercises/exercises.json` in the format above (`id`, `title`,
`difficulty`, `scenario`, `expected_concepts`, and optionally `solution` and
`tutor_notes`). To give students a different set without changing the app, share a
file instead (see *For lecturers*).
