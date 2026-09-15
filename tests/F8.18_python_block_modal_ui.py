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

    expect("cw-python-modal" in html, "Le modal Python doit utiliser son layout autonome agrandi.")
    expect('data-block-runtime-refresh="autonomous"' in html, "Le modal Python doit etre protege du rafraichissement centralise.")
    expect("python-modal-body" in html, "Le modal Python doit utiliser un layout type Codex avec navigation latérale.")
    expect('data-python-tab-id="code"' in html, "Le modal Python doit exposer l'onglet Code.")
    expect('data-python-tab-id="attributes"' in html, "Le modal Python doit exposer l'onglet Attributs.")
    expect('data-python-tab-id="runtime"' in html, "Le modal Python doit exposer l'onglet Ports & état.")
    expect("data-python-code-editor" in html, "Le modal Python doit contenir l'éditeur de code dédié.")
    expect("python-reference-panel" in html, "Le modal Python doit afficher des repères d'API à côté du code.")
    expect("data-python-line-numbers" in html, "L'éditeur Python doit afficher un gutter de numéros de lignes.")
    expect('data-python-editor-action="beautify"' in html, "Le modal Python doit exposer l'action Beautiful Python.")
    expect('data-python-editor-action="check-syntax"' in html, "Le modal Python doit exposer la vérification de syntaxe.")
    expect("data-python-editor-feedback" in html, "Le modal Python doit afficher les diagnostics de syntaxe.")
    expect("python-modal-footer" in html, "Le modal Python doit placer Appliquer dans un footer type Codex.")
    expect('data-block-config-field="script"' in html, "L'éditeur de code doit rester lié à config.script.")
    expect('data-block-config-field="timeout_sec"' in html, "Les attributs doivent conserver le timeout éditable.")
    expect('data-block-config-field="python_executable"' in html, "Les attributs doivent conserver l'exécutable Python éditable.")
    expect('data-block-config-field="params"' in html, "Les attributs doivent conserver les paramètres éditables.")
    expect("def run(inputs, outputs, params):" in html, "Le code existant doit être préchargé dans le modal.")
    expect("data-block-apply" in html, "Le modal Python doit conserver l'action Appliquer générique.")
    expect(
        {"kind": "css", "path": "assets/css/block_modal.css"} in assets,
        "Le CSS modal Python doit être déclaré comme asset block-owned.",
    )
    expect(
        {"kind": "js", "path": "assets/js/block_modal.js"} in assets,
        "Le JS modal Python doit être déclaré comme asset block-owned.",
    )
    expect(".python-modal-panel[hidden]" in css, "Les panels masqués doivent être réellement cachés par le CSS.")
    expect(".python-editor-shell" in css, "Le CSS Python doit styliser l'éditeur sombre.")
    expect("#0f172a" in css, "Le thème d'éditeur Python doit utiliser un fond sombre.")
    expect(".python-line-numbers" in css, "Le CSS Python doit styliser les numéros de lignes.")
    expect('data-python-modal-panel="code"' not in css, "Le CSS ne doit pas forcer le panel Code à rester visible.")
    expect("panel.hidden =" in js, "Le JS modal Python doit masquer les panels non actifs.")
    expect("python_check_syntax" in js, "Le JS Python doit appeler l'action de vérification syntaxique.")
    expect("python_beautify_script" in js, "Le JS Python doit appeler l'action Beautiful Python.")


def test_python_inspector_script_is_preview_only() -> None:
    """TC2 - Render the Python inspector without a dead script-edit button."""

    rendered = render_block_inspector_panel("python", {"node": python_node(), "runtime": {}})
    html = rendered.get("html") or ""

    expect("python-script-preview" in html, "L'inspector Python doit conserver un aperçu du script.")
    expect("data-open-python-script-modal" not in html, "L'inspector Python ne doit plus afficher un bouton d'édition inactif.")
    expect("openPythonScriptModalButton" not in html, "L'ancien bouton d'édition script doit être absent.")
    expect('data-block-config-field="script"' not in html, "Le script Python ne doit pas être éditable depuis l'inspector.")


def test_python_modal_ui_actions() -> None:
    """TC3 - Validate and format Python source through block-owned UI actions."""

    block = PythonBlock()
    node = python_node()
    script = 'def run(inputs, outputs, params):\n\toutputs["out"] = inputs.get("in", "")  \n\n\n'
    checked = block.handle_ui_action(node=node, action="python_check_syntax", values={"script": script})
    expect(checked.get("ok") is True, f"Le script valide doit passer la vérification: {checked}")

    beautified = block.handle_ui_action(node=node, action="python_beautify_script", values={"script": script})
    formatted = str(beautified.get("script") or "")
    expect(beautified.get("ok") is True, f"Beautiful Python doit garder un script valide: {beautified}")
    expect("\t" not in formatted, "Beautiful Python doit remplacer les tabulations par quatre espaces.")
    expect("  \n" not in formatted, "Beautiful Python doit supprimer les espaces en fin de ligne.")
    expect(not formatted.endswith("\n\n"), "Beautiful Python doit limiter les lignes vides finales.")
    expect(formatted.endswith("\n"), "Beautiful Python doit conserver une nouvelle ligne finale.")

    broken = block.handle_ui_action(
        node=node,
        action="python_check_syntax",
        values={"script": 'def run(inputs, outputs, params)\n    outputs["out"] = "nope"\n'},
    )
    expect(broken.get("ok") is False, "Un script Python invalide doit être rejeté.")
    diagnostics = broken.get("diagnostics") if isinstance(broken.get("diagnostics"), list) else []
    expect(any(item.get("severity") == "error" for item in diagnostics), "La syntaxe invalide doit produire une erreur.")


if __name__ == "__main__":
    test_python_modal_code_first_layout()
    test_python_inspector_script_is_preview_only()
    test_python_modal_ui_actions()
    print("[ok] F8.18_python_block_modal_ui")
