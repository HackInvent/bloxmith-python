#!/usr/bin/env python3
"""FB1/FB6/FB7: real installed/linked Python UI, release isolation and both runtimes."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from playwright.sync_api import sync_playwright, expect
from blocs.python.block import PythonBlock
from block_test_artifacts import artifact_path
from block_test_packages import install_test_package, surface_payload
from ui_smoke_common import (
    isolated_server, graph_payload, create_project_api, project_editor_url,
    text_node, display_node, data_edge, create_run_api, wait_for_run_predicate, stop_run_api,
    attach_console_guards, assert_no_blocking_console_errors,
)


def test_release_ui(page, server, model):
    """Check real asset mounting, edit/apply, keyboard tabs, diagnostics and responsive layouts."""
    nodes = [PythonBlock().build_node_payload(node_id=f"python-{index}", position={"x": 180 + 340 * index, "y": 160})
             for index in range(2)]
    for node, version in zip(nodes, (model["version"], "0.0.0")):
        node["block_version"] = version
    surface_payload(server, model, nodes[0])
    project = create_project_api(server, document=graph_payload("Python release UI", nodes, []))["project"]
    page.goto(project_editor_url(server.base_url, project["project_id"], workspace_project_id=project["workspace_project_id"]))
    errors = attach_console_guards(page)
    for index in (0, 1, 0):
        page.locator(f'.canvas-node[data-node-id="python-{index}"] h3').dblclick()
        modal = page.locator(".cw-python-modal")
        count = modal.locator("[data-python-code-count]")
        expect(count).to_have_text(re.compile(r"[1-9]\d* lignes? · [1-9]\d* caractères?"))
        expect(modal.locator('[data-python-modal-panel][data-python-tab-id="attributes"]')).not_to_be_visible()
        tabs = modal.locator("[data-python-modal-tab]")
        tabs.nth(1).click()
        expect(modal.locator('[data-block-config-field="timeout_sec"]')).to_be_visible()
        tabs.nth(1).press("End")
        expect(tabs.nth(2)).to_have_attribute("aria-selected", "true")
        tabs.nth(2).press("Home")
        editor = modal.locator("[data-python-code-editor]")
        expect(editor).to_be_visible()
        script = 'def run(inputs, outputs, params):\n    outputs["out"] = "saved"\n'
        editor.fill(script)
        expect(count).to_have_text(f"3 lignes · {len(script)} caractères")
        modal.locator('[data-python-editor-action="check-syntax"]').click()
        expect(modal.locator("[data-python-editor-feedback]")).to_have_class(re.compile(r"is-ok"))
        editor.fill("def broken(")
        modal.locator('[data-python-editor-action="check-syntax"]').click()
        expect(modal.locator("[data-python-editor-feedback]")).to_have_class(re.compile(r"is-error"))
        editor.fill(script.replace("    ", "\t"))
        modal.locator('[data-python-editor-action="beautify"]').click()
        expect(editor).to_have_value(script)
        expect(modal.locator("[data-block-apply]")).to_be_enabled()
        modal.locator("[data-block-apply]").click()
        # The host may keep or close the modal after applying a node patch.
        if modal.is_visible():
            modal.locator("[data-close-block-modal]").first.click()
        page.locator(f'.canvas-node[data-node-id="python-{index}"] h3').dblclick()
        expect(modal.locator("[data-python-code-editor]")).to_have_value(script)
        if index == 0:
            for width, height, label in ((1440, 900, "desktop"), (390, 740, "mobile"), (320, 568, "small")):
                page.set_viewport_size({"width": width, "height": height})
                bounds = modal.evaluate("""panel => {
                  const box=panel.getBoundingClientRect();
                  const apply=panel.querySelector('[data-block-apply]').getBoundingClientRect();
                  const close=panel.querySelector('[data-close-block-modal]').getBoundingClientRect();
                  return {inside: box.left>=0 && box.right<=innerWidth && box.bottom<=innerHeight,
                    apply: apply.bottom<=innerHeight, close: close.top>=0,
                    overflow: panel.scrollWidth>panel.clientWidth+1};
                }""")
                page.screenshot(path=artifact_path(f"python-release-{label}.png"))
                assert bounds["inside"] and bounds["apply"] and bounds["close"] and not bounds["overflow"], (label, bounds)
            page.set_viewport_size({"width": 1440, "height": 900})
        # The stylesheet must never affect a different release's or the shell's elements.
        assert page.evaluate("""() => {
          const probe=document.createElement('div'); probe.className='cw-python-modal';
          document.body.append(probe); const display=getComputedStyle(probe).display;
          probe.remove(); return display==='block';
        }""")
        modal.locator("[data-close-block-modal]").first.click()
    assert page.evaluate("!window.CWBlockUiBlocks?.python"), "No unversioned JS registration"
    assert_no_blocking_console_errors(errors)


def test_release_runtimes(server, model):
    """Exercise the same package under both engines, including the linked isolation fixture."""
    for mode in ("centralized", "zeromq_active"):
        for version in (model["version"], "0.0.0"):
            node = PythonBlock().build_node_payload(node_id="python-runtime")
            node["block_version"] = version
            document = graph_payload("Python package runtime", [
                text_node("seed", "Seed", "release-runtime-ok", 0, 0), node, display_node("sink", "Sink", 600, 0),
            ], [data_edge("input", "seed", 1, node["id"], 1), data_edge("output", node["id"], 1, "sink", 1)])
            created = create_run_api(server, document, runtime_mode=mode)
            try:
                run = wait_for_run_predicate(server, created["run_id"],
                    lambda run: run.get("node_statuses", {}).get("sink") == "success" or run.get("status") == "failed",
                    "Python package did not deliver its output", timeout_sec=25)
                assert run.get("status") != "failed", run.get("logs")
                assert "release-runtime-ok" in str(run.get("output_values")), run.get("output_values")
            finally:
                stop_run_api(server, created["run_id"])
            print(f"[ok] Python {version} {mode}", flush=True)


def main():
    """Install the current package and a linked fixture without using a developer instance."""
    with isolated_server() as server, sync_playwright() as playwright:
        model = install_test_package(server, "python", variant=True)
        browser = playwright.chromium.launch(headless=True)
        try:
            test_release_ui(browser.new_page(viewport={"width": 1440, "height": 900}), server, model)
        finally:
            browser.close()
        test_release_runtimes(server, model)
    print("[ok] F8.19_python_release_ui")


if __name__ == "__main__":
    main()
