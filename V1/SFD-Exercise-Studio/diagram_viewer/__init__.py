"""
Read-only diagram viewer.

Renders a CLD or an SFD passed from Python — no editing tools, no toolbar.
Used to display the AI-generated model solution beside the student's own work.
"""

import os
import streamlit.components.v1 as components

_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND = os.path.join(_DIR, "frontend")

_component = components.declare_component("diagram_viewer", path=_FRONTEND)


def diagram_viewer(key, diagram, kind):
    """
    Display a diagram read-only.

    Parameters
    ----------
    key : str
        Unique Streamlit key.
    diagram : dict
        A CLD ({"nodes", "edges"}) or SFD
        ({"stocks", "flows", "auxiliaries", "clouds", "connectors"}) payload.
    kind : str
        "cld" or "sfd" — selects how the diagram is interpreted and styled.
    """
    return _component(diagram=diagram or {}, kind=kind, key=key, default=None)
