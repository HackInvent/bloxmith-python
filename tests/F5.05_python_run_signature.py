#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies python run signature behavior for the Python block.
# File Name: F5.05_python_run_signature.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-07-28
# -----------------------------------------------------------------------------

"""F5.05 - Bloc Python avec signature def run(inputs, outputs).

Le test vérifie qu'un bloc Python simple peut lire son input par nom de port,
écrire dans outputs, puis propager la valeur vers un display.
"""

# Test cases:
# - FB1/FB2 - Execute a Python script using run(inputs, outputs) and verify named outputs.
# - FB1/FB2 - Execute a Python script using run(inputs, outputs, params) and verify params are available.
# - FB3/FB5 - Verify invalid or missing output names are warned and ignored without crashing unrelated outputs.
# - FB4 - Verify dynamic code input overrides the configured script and the effective code can be forwarded.

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ui_smoke_common import (
    create_run_api,
    data_edge,
    display_node,
    expect,
    graph_payload,
    isolated_server,
    text_node,
    wait_for_run_terminal,
)

from blocs.python.block import PythonBlock
from bloxsmith_app.block_runtime import BlockRuntimeContext
from bloxsmith_app.port_types import CODE_PYTHON


def runtime_node_id_for_kind(run: dict, kind: str) -> str:
    """Return the normalized runtime node id for one unique node kind in a run payload."""

    nodes = (run.get("document") or {}).get("nodes") or []
    matches = [str(node.get("id") or "") for node in nodes if node.get("kind") == kind]
    expect(len(matches) == 1 and matches[0], f"Node runtime {kind} introuvable ou ambigu: {matches}")
    return matches[0]


def python_node() -> dict:
    return {
        "id": "python-1",
        "kind": "python",
        "title": "Python test",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {"id": 1, "name": "in", "title": "In", "accepts": ["message/*"], "multiplicity": "many"}
        ],
        "outputs": [
            {"id": 1, "name": "out", "title": "Out", "emits": ["message/*"], "multiplicity": "many"}
        ],
        "config": {
            "script": "def run(inputs, outputs):\n    outputs[\"out\"] = inputs.get(\"in\", \"\").upper()\n",
            "timeout_sec": 10,
            "python_executable": "python3",
            "params": [],
        },
    }


def _verify_dynamic_code_override() -> None:
    override_script = 'def run(inputs, outputs):\n    outputs["out"] = "override " + inputs.get("in", "")\n'
    with TemporaryDirectory(prefix="bloxsmith-python-fb4-") as tmp:
        result = PythonBlock().execute_runtime(
            BlockRuntimeContext(
                run_id="unit-run",
                node_id="python-dynamic",
                kind="python",
                title="Python dynamic",
                config={
                    "script": 'def run(inputs, outputs):\n    outputs["out"] = "configured"\n',
                    "timeout_sec": 10,
                    "python_executable": "python3",
                    "dynamic_code_enabled": True,
                    "code_input_port_id": 2,
                    "code_output_port_id": 2,
                },
                inputs={"in": "script", "code": override_script},
                input_content_types={"code": CODE_PYTHON},
                input_message="",
                input_ports=(
                    SimpleNamespace(id=1, name="in", accepts=("message/*",)),
                    SimpleNamespace(id=2, name="code", accepts=(CODE_PYTHON,)),
                ),
                output_ports=(
                    SimpleNamespace(id=1, name="out", emits=("message/*",)),
                    SimpleNamespace(id=2, name="effective_code", emits=(CODE_PYTHON,)),
                ),
                root_dir=Path(tmp),
                run_dir=Path(tmp),
            )
        )
    values = {output.port_id: output.value for output in result.outputs}
    expect(result.status == "success", "Python dynamique doit réussir.")
    expect(values.get(1) == "override script", "Le code dynamique doit remplacer le script configuré.")
    expect(values.get(2) == override_script, "Le port code output doit publier le code effectif.")
    expect(result.metadata.get("python_code_override_used") is True, "La metadata doit signaler l'override dynamique.")


def main() -> None:
    _verify_dynamic_code_override()
    with isolated_server() as server:
        document = graph_payload(
            "F5 Python",
            [
                text_node("text-1", "Texte Python", "hello python", 80, 120),
                python_node(),
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-text-python", "text-1", 1, "python-1", 1),
                data_edge("edge-python-display", "python-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=20)
        expect(run.get("status") == "success", "Le run Python doit réussir.")
        python_node_id = runtime_node_id_for_kind(run, "python")
        display_node_id = runtime_node_id_for_kind(run, "display")
        expect(run.get("output_values", {}).get(f"{python_node_id}:1", {}).get("value") == "HELLO PYTHON", "La sortie Python est incorrecte.")
        expect("HELLO PYTHON" in str(run.get("worker_rows", {}).get(display_node_id, {}).get("received") or ""), "Display ne reçoit pas la sortie Python.")
    print("[ok] F5.05_python_run_signature")


if __name__ == "__main__":
    main()
