#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies active Python behavior when feedback edges transport values.
# File Name: F11.07_active_python_feedback_loop.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-06-21
# -----------------------------------------------------------------------------

"""F11.07 - Feedback transport sur workers Python actifs.

Le test lance un graphe ZeroMQ actif avec une arête feedback vers Python. Cette
arête garde son rendu visuel, mais elle est compilée en subscription et met à
jour l'attribut d'input cible comme une route runtime.
"""

import time

from ui_smoke_common import (
    data_edge,
    display_node,
    expect,
    feedback_edge,
    get_run_api,
    graph_payload,
    http_json,
    isolated_server,
    prepare_run_api,
    stop_run_api,
    text_node,
    wait_for_run_predicate,
)


def active_control(server, run_id: str, action: str, node_id: str) -> dict:
    """Send a targeted active runtime control action for one node."""

    return http_json(
        server.base_url,
        f"/api/runs/{run_id}/active/control",
        method="POST",
        payload={"action": action, "node_id": node_id},
    )


def python_node(node_id: str, title: str, prefix: str, x: int, y: int) -> dict:
    """Build a Python node that prefixes the value received on input `in`."""

    script = f"""def run(inputs, outputs):
    outputs['out'] = {prefix!r} + ':' + str(inputs.get('in') or '')
"""
    return {
        "id": node_id,
        "kind": "python",
        "title": title,
        "position": {"x": x, "y": y},
        "inputs": [
            {"id": 1, "name": "in", "title": "In", "accepts": ["message/*"], "multiplicity": "many"}
        ],
        "outputs": [
            {"id": 1, "name": "out", "title": "Out", "emits": ["message/*"], "multiplicity": "many"}
        ],
        "config": {
            "script": script,
            "timeout_sec": 10,
            "python_executable": "python3",
            "params": [],
        },
    }


def python_node_passthrough_trigger(node_id: str, title: str, x: int, y: int) -> dict:
    """Build a Python node that echoes its single trigger input."""

    return {
        "id": node_id,
        "kind": "python",
        "title": title,
        "position": {"x": x, "y": y},
        "inputs": [
            {
                "id": 1,
                "name": "trigger",
                "title": "Trigger",
                "accepts": ["message/*", "control/trigger"],
                "multiplicity": "many",
            }
        ],
        "outputs": [
            {"id": 1, "name": "out", "title": "Out", "emits": ["message/*"], "multiplicity": "many"}
        ],
        "config": {
            "script": """def run(inputs, outputs):
    outputs['out'] = str(inputs.get('trigger') or '')
""",
            "timeout_sec": 10,
            "python_executable": "python3",
            "params": [],
        },
    }


def verify_feedback_transport_to_python(server) -> None:
    """Feedback should subscribe python-b to python-a output in active mode."""

    document = graph_payload(
        "F11 active python feedback transport",
        [
            text_node("text-1", "Seed", "seed", 80, 140),
            python_node("python-a", "Python A", "A", 360, 140),
            python_node("python-b", "Python B", "B", 640, 140),
            display_node("display-1", "Affichage", 920, 140),
        ],
        [
            data_edge("edge-text-a", "text-1", 1, "python-a", 1),
            feedback_edge("edge-a-b", "python-a", 1, "python-b", 1),
            data_edge("edge-b-display", "python-b", 1, "display-1", 1),
        ],
    )
    prepared = prepare_run_api(server, document, runtime_mode="zeromq_active")
    run_id = str(prepared.get("run_id") or "")

    try:
        active_control(server, run_id, "publish_seed", "text-1")
        state = wait_for_run_predicate(
            server,
            run_id,
            lambda item: item.get("output_values", {}).get("python-b:1", {}).get("value") == "B:A:seed",
            "Le feedback doit transporter A:seed jusqu'au bloc python-b.",
            timeout_sec=15,
        )
        logs = "\n".join(state.get("logs", []))
        expect(state.get("output_values", {}).get("python-a:1", {}).get("value") == "A:seed", "python-a doit consommer le flux data.")
        expect("fallback centralized" not in logs, "Le run ne doit pas fallback centralisé.")
    finally:
        stop_run_api(server, run_id)


def verify_required_many_input_waits_for_all_data_messages(server) -> None:
    """A required many-input port waits until every data route has delivered."""

    document = graph_payload(
        "F11 active python same port data readiness",
        [
            text_node("text-a", "Text A", "alpha", 80, 140),
            text_node("text-b", "Text B", "bravo", 80, 260),
            python_node_passthrough_trigger("python-a", "Python A", 360, 140),
            display_node("display-1", "Affichage", 640, 140),
        ],
        [
            data_edge("edge-text-a-python", "text-a", 1, "python-a", 1),
            data_edge("edge-text-b-python", "text-b", 1, "python-a", 1),
            data_edge("edge-python-display", "python-a", 1, "display-1", 1),
        ],
    )
    prepared = prepare_run_api(server, document, runtime_mode="zeromq_active")
    run_id = str(prepared.get("run_id") or "")

    try:
        active_control(server, run_id, "publish_seed", "text-a")
        time.sleep(0.4)
        partial_state = get_run_api(server, run_id)
        expect(
            "python-a:1" not in (partial_state.get("output_values") or {}),
            "Le bloc Python ne doit pas s'executer avant que toutes les routes required/many aient livre.",
        )

        active_control(server, run_id, "publish_seed", "text-b")
        state = wait_for_run_predicate(
            server,
            run_id,
            lambda item: "python-a:1" in (item.get("output_values") or {}),
            "Toutes les routes data d'un port required/many doivent declencher le bloc Python.",
            timeout_sec=10,
        )
        expect(
            state.get("output_values", {}).get("python-a:1", {}).get("value") == "alpha\n\nbravo",
            "Le bloc Python doit joindre les valeurs de toutes les routes du port required/many.",
        )
    finally:
        stop_run_api(server, run_id)


def main() -> None:
    with isolated_server() as server:
        verify_feedback_transport_to_python(server)
        verify_required_many_input_waits_for_all_data_messages(server)
    print("[ok] F11.07_active_python_feedback_loop")


if __name__ == "__main__":
    main()
