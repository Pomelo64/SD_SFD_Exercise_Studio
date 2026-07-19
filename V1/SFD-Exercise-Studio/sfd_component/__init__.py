"""
Python side of the SFD (Stock & Flow Diagram) drawing component.

Declares the static-HTML frontend as a bidirectional Streamlit component so the
diagram drawn in the browser is returned to Python when the user submits.

No structural restrictions are imposed in the editor — students may connect any
element to any other. Structural mistakes are caught by the LLM feedback, so
errors become a teaching opportunity rather than something the UI prevents.
"""

import os
import streamlit.components.v1 as components

_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND = os.path.join(_DIR, "frontend")

_component = components.declare_component("sfd_canvas", path=_FRONTEND)


def sfd_canvas(key, initial=None):
    """
    Render the SFD drawing canvas and return the most recently submitted diagram.

    Parameters
    ----------
    key : str
        Unique key for this canvas instance (use one per exercise).
    initial : dict or None
        Optional diagram to pre-load, shaped like the return value.

    Returns
    -------
    dict or None
        None until the user clicks "Submit diagram". Afterwards a typed SFD:
            {
              "submitted_at": <epoch ms>,
              "stocks":      [{"label": str, "x": int, "y": int}, ...],
              "flows":       [{"label": str, "from": str|null,
                               "to": str|null}, ...],
              "auxiliaries": [{"label": str, "x": int, "y": int}, ...],
              "clouds":      [{"label": str, "x": int, "y": int}, ...],
              "connectors":  [{"from": str, "to": str}, ...]
            }
        For flows, `from`/`to` are the labels of the stock or cloud at each end
        (null if the user left an end unattached).
    """
    return _component(initial=initial or {}, key=key, default=None)
