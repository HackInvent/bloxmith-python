#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies Python block-owned modal UI rendering.
# File Name: F8.18_python_block_modal_ui.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2026-05-17
# -----------------------------------------------------------------------------

"""F8.18 - Python modal exposes a code-first tabbed editor."""

# Test cases:
# - FB6 - Render a code-first modal with separate Code, Attributes, and Runtime panels.
# - FB6 - Keep the Python inspector as a script preview and avoid duplicate editing controls.
# - FB7 - Execute block-owned syntax checking and conservative formatting actions.

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bloxsmith_app.block_ui import render_block_inspector_panel, render_block_modal
from ui_smoke_common import expect
from blocs.python.block import PythonBlock


def python_node() -> dict:
    """Return a representative serialized Python node for modal rendering tests."""

    return {
        "id": "python-1",
        "kind": "python",
        "type": "python",
        "title": "Python ergonomique",
        "inputs": [{"id": 1, "name": "in", "accepts": ["message/*"]}],
        "outputs": [{"id": 1, "name": "out", "emits": ["message/*"]}],
        "config": {
            "script": 'def run(inputs, outputs, params):\n    outputs["out"] = inputs.get("in", "")\n',
            "timeout_sec": 25,
            "python_executable": "python3",
            "params": [{"name": "prefix", "value": "demo"}],
            "dynamic_code_enabled": True,
            "code_input_port_id": None,
            "code_output_port_id": None,
        },
    }


def test_python_modal_code_first_layout() -> None:
    """TC1 - Render the Python modal with dedicated Code, Attributes, and Runtime tabs."""

    rendered = render_block_modal("python", {"node": python_node(), "runtime": {}})
    html = rendered.get("html") or ""
    assets = PythonBlock().model["ui_assets"]["modal"]
    css = (ROOT / "blocs/python/assets/css/block_modal.css").read_text(encoding="utf-8")
    js = (ROOT / "blocs/python/assets/js/block_modal.js").read_text(encoding="utf-8")

    expect("cw-python-modal" in html, "The Python modal must use its own enlarged layout.")
    expect('data-block-runtime-refresh="autonomous"' in html, "The Python modal must be protected from the centralized refresh.")
    expect("python-modal-body" in html, "The Python modal must use a Codex-like layout with side navigation.")
    expect('data-python-tab-id="code"' in html, "The Python modal must expose the Code tab.")
    expect('data-python-tab-id="attributes"' in html, "The Python modal must expose the Attributes tab.")
    expect('data-python-tab-id="runtime"' in html, "The Python modal must expose the Ports and state tab.")
    expect("data-python-code-editor" in html, "The Python modal must contain its dedicated code editor.")
    expect("python-reference-panel" in html, "The Python modal must show API reminders next to the code.")
    expect("data-python-line-numbers" in html, "The Python editor must show a line-number gutter.")
    expect('data-python-editor-action="beautify"' in html, "The Python modal must expose the Beautiful Python action.")
    expect('data-python-editor-action="check-syntax"' in html, "The Python modal must expose the syntax check.")
    expect("data-python-editor-feedback" in html, "The Python modal must show the syntax diagnostics.")
    expect("python-modal-footer" in html, "The Python modal must place Apply in a Codex-like footer.")
    expect('data-block-config-field="script"' in html, "The code editor must stay bound to config.script.")
    expect('data-block-config-field="timeout_sec"' in html, "The attributes must keep the timeout editable.")
    expect('data-block-config-field="python_executable"' in html, "The attributes must keep the Python executable editable.")
    expect('data-block-config-field="params"' in html, "The attributes must keep the parameters editable.")
    expect("def run(inputs, outputs, params):" in html, "The existing code must be preloaded in the modal.")
    expect("data-block-apply" in html, "The Python modal must keep the generic Apply action.")
    expect(
        {"kind": "css", "path": "assets/css/block_modal.css"} in assets,
        "The Python modal CSS must be declared as a block-owned asset.",
    )
    expect(
        {"kind": "js", "path": "assets/js/block_modal.js"} in assets,
        "The Python modal JS must be declared as a block-owned asset.",
    )
    expect(".python-modal-panel[hidden]" in css, "Hidden panels must really be hidden by the CSS.")
    expect(".python-editor-shell" in css, "The Python CSS must style the dark editor.")
    expect("#0f172a" in css, "The Python editor theme must use a dark background.")
    expect(".python-line-numbers" in css, "The Python CSS must style the line numbers.")
    expect('data-python-modal-panel="code"' not in css, "The CSS must not force the Code panel to stay visible.")
    expect("panel.hidden =" in js, "The Python modal JS must hide the inactive panels.")
    expect("python_check_syntax" in js, "The Python JS must call the syntax-check action.")
    expect("python_beautify_script" in js, "The Python JS must call the Beautiful Python action.")


def test_python_inspector_script_is_preview_only() -> None:
    """TC2 - Render the Python inspector without a dead script-edit button."""

    rendered = render_block_inspector_panel("python", {"node": python_node(), "runtime": {}})
    html = rendered.get("html") or ""

    expect("python-script-preview" in html, "The Python inspector must keep a script preview.")
    expect("data-open-python-script-modal" not in html, "The Python inspector must no longer show a dead edit button.")
    expect("openPythonScriptModalButton" not in html, "The old script-edit button must be gone.")
    expect('data-block-config-field="script"' not in html, "The Python script must not be editable from the inspector.")


def test_python_modal_ui_actions() -> None:
    """TC3 - Validate and format Python source through block-owned UI actions."""

    block = PythonBlock()
    node = python_node()
    script = 'def run(inputs, outputs, params):\n\toutputs["out"] = inputs.get("in", "")  \n\n\n'
    checked = block.handle_ui_action(node=node, action="python_check_syntax", values={"script": script})
    expect(checked.get("ok") is True, f"The valid script must pass the check: {checked}")

    beautified = block.handle_ui_action(node=node, action="python_beautify_script", values={"script": script})
    formatted = str(beautified.get("script") or "")
    expect(beautified.get("ok") is True, f"Beautiful Python must keep the script valid: {beautified}")
    expect("\t" not in formatted, "Beautiful Python must replace tabs with four spaces.")
    expect("  \n" not in formatted, "Beautiful Python must remove trailing spaces.")
    expect(not formatted.endswith("\n\n"), "Beautiful Python must limit the trailing blank lines.")
    expect(formatted.endswith("\n"), "Beautiful Python must keep a final newline.")

    broken = block.handle_ui_action(
        node=node,
        action="python_check_syntax",
        values={"script": 'def run(inputs, outputs, params)\n    outputs["out"] = "nope"\n'},
    )
    expect(broken.get("ok") is False, "An invalid Python script must be rejected.")
    diagnostics = broken.get("diagnostics") if isinstance(broken.get("diagnostics"), list) else []
    expect(any(item.get("severity") == "error" for item in diagnostics), "Invalid syntax must produce an error.")


if __name__ == "__main__":
    test_python_modal_code_first_layout()
    test_python_inspector_script_is_preview_only()
    test_python_modal_ui_actions()
    print("[ok] F8.18_python_block_modal_ui")
