# -----------------------------------------------------------------------------
# Role: Implements the Python block runtime and UI contract.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-05-15
# -----------------------------------------------------------------------------

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import json
import re
import subprocess
import tempfile
import time

from bloxsmith_app.block_api import (
    APPLICATION_JSON,
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    CODE_PYTHON,
    render_inspector_template,
    render_node_card_template,
    TEXT_PLAIN,
    validate_python_script_payload,
)


DEFAULT_PYTHON_SCRIPT = 'def run(inputs, outputs, params):\n    outputs["out"] = inputs.get("in", "")\n'
DEFAULT_TIMEOUT_SEC = 10
DEFAULT_PYTHON_EXECUTABLE = "python3"


# Functional behavior:
# FB1 - Execute user Python code in an isolated subprocess with serialized inputs, params, and output definitions.
# FB2 - Accept run(inputs, outputs) and run(inputs, outputs, params) signatures.
# FB3 - Normalize returned output mappings into configured block outputs and ignore unknown output names with a warning.
# FB4 - Support dynamic code input/output ports for script override and forwarding.
# FB5 - Surface timeouts, process failures, missing run functions, and invalid output files as block failures.
# FB6 - Render a code-first modal where Python source editing is separated from attributes and runtime details.
# FB7 - Provide block-owned modal tooling for conservative formatting and syntax diagnostics.
class PythonBlockError(ValueError):
    """Raised when a python block cannot execute its inline script."""


class PythonBlock(BlockDefinition):
    """Autonomous block implementation for `PythonBlock`."""
    kind = "python"


    def render_modal(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the Python block modal with a dedicated code editor tab."""

        config = self._ui_config(node)
        template = (self.directory / "block_modal.html").read_text(encoding="utf-8")
        title = str(node.get("title") or self.default_title())
        replacements = {
            "node_id": escape(str(node.get("id") or ""), quote=True),
            "node_title": escape(title),
            "node_kind": escape(self.kind, quote=True),
            "node_kind_title": escape(str(self.model.get("title") or self.default_title())),
            "script": escape(config["script"]),
            "title_field_html": self._render_modal_title_field(title),
            "attributes_html": self._render_modal_attributes(config),
            "ports_html": self._render_generic_modal_ports(node),
            "runtime_html": self._render_generic_modal_runtime(payload or {}),
        }
        html = template
        for key, value in replacements.items():
            html = html.replace(f"{{{{ {key} }}}}", str(value))
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "node_kind": self.kind,
            },
        }

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the Python canvas card body from the block-owned template."""

        config = self._ui_config(node)
        params = config["params"] if isinstance(config.get("params"), list) else []
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["python-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "preview": "def run(inputs, outputs, params)",
                "params": f"{len(params)} param{'s' if len(params) > 1 else ''}",
                "timeout": f"{config['timeout_sec']}s",
            },
        )

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the block-owned inspector panel HTML for the selected node.

        Args:
            node: Serialized graph node handled by the block.
            payload: Optional UI or runtime payload provided by the framework.
        """
        config = self._ui_config(node)
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=(
                template
                .replace("{{ script_preview }}", escape(self._script_preview(config["script"])))
                .replace("{{ dynamic_checked }}", "checked" if config["dynamic_code_enabled"] else "")
                .replace("{{ timeout_sec }}", str(config["timeout_sec"]))
                .replace("{{ params_html }}", self._render_params_rows(config["params"]))
            ),
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
        )
        return {"html": html, "context": {"node_id": str(node.get("id") or ""), "full_panel": True}}

    def handle_ui_action(
        self,
        *,
        node: dict[str, Any],
        action: str,
        values: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle Python-owned modal actions without adding frontend framework branching.

        Args:
            node: Serialized Python node being edited.
            action: Action emitted by the Python modal asset.
            values: Action values, primarily the current unsaved script text.
            payload: Optional graph/UI context provided by the generic block UI layer.

        Returns:
            A block UI action result containing diagnostics and, for formatting,
            the rewritten script text.
        """

        if action == "python_check_syntax":
            return self._handle_python_check_syntax(node=node, values=values)
        if action == "python_beautify_script":
            return self._handle_python_beautify_script(node=node, values=values)
        return super().handle_ui_action(node=node, action=action, values=values, payload=payload)

    def _ui_config(self, node: dict[str, Any]) -> dict[str, Any]:
        """Provide internal PythonBlock behavior for `_ui_config`.

        Args:
            node: Serialized graph node handled by the block.
        """
        raw = node.get("python") if isinstance(node.get("python"), dict) else node.get("config")
        raw = raw if isinstance(raw, dict) else {}
        return {
            "script": str(raw.get("script") if raw.get("script") is not None else DEFAULT_PYTHON_SCRIPT),
            "timeout_sec": self._normalize_timeout(raw.get("timeout_sec")),
            "python_executable": str(raw.get("python_executable") or DEFAULT_PYTHON_EXECUTABLE).strip()
            or DEFAULT_PYTHON_EXECUTABLE,
            "params": self._normalize_params(raw.get("params")),
            "dynamic_code_enabled": bool(raw.get("dynamic_code_enabled", False)),
            "code_input_port_id": self._normalize_optional_port_id(raw.get("code_input_port_id")),
            "code_output_port_id": self._normalize_optional_port_id(raw.get("code_output_port_id")),
        }

    def _handle_python_check_syntax(self, *, node: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        """Validate the unsaved modal script against the Python block contract."""

        script = str(values.get("script") if isinstance(values, dict) and values.get("script") is not None else "")
        return self._validate_script_for_ui(node=node, script=script)

    def _handle_python_beautify_script(self, *, node: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        """Return a safely formatted script when syntax is valid.

        The formatter is intentionally conservative: it normalizes tabs,
        trailing spaces, blank lines, and final newline without using AST
        rewriting, so comments and string literals remain untouched.
        """

        script = str(values.get("script") if isinstance(values, dict) and values.get("script") is not None else "")
        validation = self._validate_script_for_ui(node=node, script=script)
        if not validation.get("ok"):
            return {**validation, "script": script}
        formatted = self._beautify_script_preserving_behavior(script)
        return {**self._validate_script_for_ui(node=node, script=formatted), "script": formatted}

    def _validate_script_for_ui(self, *, node: dict[str, Any], script: str) -> dict[str, Any]:
        """Validate script text with the node outputs as expected output names."""

        result = validate_python_script_payload(
            {
                "script": script,
                "outputs": node.get("outputs") if isinstance(node.get("outputs"), list) else [],
            }
        )
        result["action_scope"] = "python_block_modal"
        return result

    def _beautify_script_preserving_behavior(self, script: str) -> str:
        """Normalize Python source layout without semantic rewrites."""

        lines = str(script or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        normalized = [line.replace("\t", "    ").rstrip() for line in lines]
        while normalized and not normalized[0].strip():
            normalized.pop(0)
        while normalized and not normalized[-1].strip():
            normalized.pop()

        compacted: list[str] = []
        blank_count = 0
        for line in normalized:
            if line.strip():
                blank_count = 0
                compacted.append(line)
                continue
            blank_count += 1
            if blank_count <= 2:
                compacted.append("")

        return ("\n".join(compacted) if compacted else "").rstrip() + "\n"

    def _script_preview(self, script: str) -> str:
        """Provide internal PythonBlock behavior for `_script_preview`.

        Args:
            script: Script value used by this block helper.
        """
        lines = str(script or "").splitlines()
        return "\n".join(lines[:8]) if lines else DEFAULT_PYTHON_SCRIPT

    def _render_params_rows(self, params: list[dict[str, str]]) -> str:
        """Render a block-owned HTML fragment used by the modal or inspector.

        Args:
            params: Additional action or runtime parameters.
        """
        if not params:
            return '<div class="python-params-empty">Aucun paramètre. Ajoute un paramètre pour l’utiliser avec params["nom"].</div>'
        rows: list[str] = []
        for index, param in enumerate(params):
            rows.append(
                "\n".join(
                    [
                        f'<div class="python-param-row" data-index="{index}">',
                        (
                            f'  <input type="text" value="{escape(param["name"])}" placeholder="mon_param_1" '
                            f'data-python-param-field="name" data-block-config-list="params" '
                            f'data-block-config-list-field="name" data-index="{index}" autocomplete="off" />'
                        ),
                        (
                            f'  <input type="text" value="{escape(param["value"])}" placeholder="Valeur" '
                            f'data-python-param-field="value" data-block-config-list="params" '
                            f'data-block-config-list-field="value" data-index="{index}" autocomplete="off" />'
                        ),
                        (
                            f'  <button type="button" class="ghost-btn python-param-remove" '
                            f'data-python-param-action="delete" data-index="{index}" title="Supprimer le paramètre">×</button>'
                        ),
                        "</div>",
                    ]
                )
            )
        return "\n".join(rows)

    def _render_modal_title_field(self, title: str) -> str:
        """Render the editable title field without the generic modal Apply toolbar."""

        return (
            '<div class="field-group">'
            "<label>Nom du bloc</label>"
            f'<input data-block-title-field type="text" autocomplete="off" value="{escape(title, quote=True)}" />'
            "</div>"
        )

    def _render_modal_optional_port_id(self, *, label: str, field: str, value: int | None) -> str:
        """Render an optional numeric port-id config field for dynamic-code routing."""

        rendered_value = "" if value is None else str(value)
        return (
            '<div class="field-group">'
            f"<label>{escape(label)}</label>"
            f'<input data-block-config-field="{escape(field, quote=True)}" data-block-value-type="integer" '
            f'type="number" min="1" step="1" value="{escape(rendered_value, quote=True)}" '
            'placeholder="Aucun port dédié" />'
            "</div>"
        )

    def _render_modal_attributes(self, config: dict[str, Any]) -> str:
        """Render Python modal attributes that are not the main source editor."""

        params_json = json.dumps(config["params"], ensure_ascii=False, indent=2)
        return "\n".join(
            [
                '<div class="python-modal-config-grid">',
                '  <div class="field-group">',
                "    <label>Timeout secondes</label>",
                (
                    f'    <input data-block-config-field="timeout_sec" data-block-value-type="integer" '
                    f'type="number" min="1" max="3600" step="1" value="{config["timeout_sec"]}" />'
                ),
                "  </div>",
                '  <div class="field-group">',
                "    <label>Exécutable Python</label>",
                (
                    f'    <input data-block-config-field="python_executable" type="text" '
                    f'value="{escape(config["python_executable"], quote=True)}" autocomplete="off" spellcheck="false" />'
                ),
                "  </div>",
                "</div>",
                '<label class="checkbox-line python-modal-checkbox">',
                (
                    f'  <input data-block-config-field="dynamic_code_enabled" data-block-value-type="boolean" '
                    f'type="checkbox" {"checked" if config["dynamic_code_enabled"] else ""} />'
                ),
                "  <span>Modification dynamique : autoriser un input à remplacer le code effectif.</span>",
                "</label>",
                '<div class="python-modal-config-grid">',
                self._render_modal_optional_port_id(
                    label="Port d'entrée code",
                    field="code_input_port_id",
                    value=config.get("code_input_port_id"),
                ),
                self._render_modal_optional_port_id(
                    label="Port de sortie code",
                    field="code_output_port_id",
                    value=config.get("code_output_port_id"),
                ),
                "</div>",
                '<div class="field-group">',
                "  <label>Paramètres JSON</label>",
                (
                    '  <textarea class="python-params-json" data-block-config-field="params" '
                    'data-block-value-type="json" rows="8" spellcheck="false">'
                    f"{escape(params_json)}"
                    "</textarea>"
                ),
                '  <p class="field-hint">Format attendu : [{"name": "mon_param", "value": "ma valeur"}].</p>',
                "</div>",
            ]
        )

    def normalize_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize raw node configuration into safe block runtime settings.

        Args:
            config: Raw or normalized block configuration.
        """
        raw_config = config if isinstance(config, dict) else {}
        raw_script = raw_config.get("script", DEFAULT_PYTHON_SCRIPT)
        script = DEFAULT_PYTHON_SCRIPT if raw_script is None else str(raw_script)
        return {
            "script": script,
            "timeout_sec": self._normalize_timeout(raw_config.get("timeout_sec")),
            "python_executable": str(raw_config.get("python_executable") or DEFAULT_PYTHON_EXECUTABLE).strip()
            or DEFAULT_PYTHON_EXECUTABLE,
            "params": self._normalize_params(raw_config.get("params")),
            "dynamic_code_enabled": bool(
                raw_config.get("dynamic_code_enabled", raw_config.get("dynamicCodeEnabled", False))
            ),
            "code_input_port_id": self._normalize_optional_port_id(
                raw_config.get("code_input_port_id")
            ),
            "code_output_port_id": self._normalize_optional_port_id(
                raw_config.get("code_output_port_id")
            ),
        }

    def execute(
        self,
        *,
        root_dir: Path,
        config: dict[str, Any] | None,
        inputs: dict[str, Any],
        work_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Execute the block business logic with normalized inputs and configuration.

        Args:
            root_dir: Directory path used by the block runtime.
            config: Raw or normalized block configuration.
            inputs: Input values received by the block.
            work_dir: Directory path used by the block runtime.
        """
        normalized_config = self.normalize_config(config)
        script = str(normalized_config["script"])
        timeout_sec = int(normalized_config["timeout_sec"])
        python_executable = str(normalized_config["python_executable"])
        root = root_dir.resolve()
        temp_parent = (work_dir or root).resolve()
        temp_parent.mkdir(parents=True, exist_ok=True)

        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="python-block-", dir=str(temp_parent)) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            script_path = temp_dir / "user_script.py"
            wrapper_path = temp_dir / "runner.py"
            inputs_path = temp_dir / "inputs.json"
            params_path = temp_dir / "params.json"
            outputs_path = temp_dir / "outputs.json"

            script_path.write_text(script, encoding="utf-8")
            inputs_path.write_text(json.dumps(inputs or {}, ensure_ascii=False), encoding="utf-8")
            params_path.write_text(
                json.dumps(self._params_dict(normalized_config["params"]), ensure_ascii=False),
                encoding="utf-8",
            )
            wrapper_path.write_text(self._runner_source(), encoding="utf-8")

            command = [
                python_executable,
                str(wrapper_path),
                str(script_path),
                str(inputs_path),
                str(params_path),
                str(outputs_path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(root),
                    text=True,
                    capture_output=True,
                    timeout=timeout_sec,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
                stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
                return {
                    "status": "timeout",
                    "exit_code": -1,
                    "stdout": stdout,
                    "stderr": stderr,
                    "outputs": {},
                    "duration": round(time.perf_counter() - started, 3),
                    "error": f"Timeout Python apres {timeout_sec}s.",
                }
            except OSError as exc:
                raise PythonBlockError(f"Execution Python impossible: {exc}") from exc

            raw_outputs: dict[str, Any] = {}
            if outputs_path.exists():
                try:
                    parsed_outputs = json.loads(outputs_path.read_text(encoding="utf-8") or "{}")
                except json.JSONDecodeError as exc:
                    raise PythonBlockError(f"outputs.json invalide: {exc}") from exc
                if isinstance(parsed_outputs, dict):
                    raw_outputs = parsed_outputs

            return {
                "status": "success" if completed.returncode == 0 else "failed",
                "exit_code": completed.returncode,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "outputs": raw_outputs,
                "duration": round(time.perf_counter() - started, 3),
                "error": "" if completed.returncode == 0 else (completed.stderr or completed.stdout or "Script Python en echec."),
            }

    def serialize_output_value(self, value: Any) -> str:
        """Serialize a block output value for runtime publication.

        Args:
            value: Value to normalize, render, serialize, or process.
        """
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(value, (bool, int, float)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Execute the block through the generic runtime context and return runtime outputs.

        Args:
            context: Generic runtime context injected by the execution engine.
        """
        normalized_config = self.normalize_config(context.config)
        effective_script, code_override_used, code_override_label = self._effective_script(context, normalized_config)
        effective_config = dict(normalized_config)
        effective_config["script"] = effective_script
        dynamic_code_enabled = bool(effective_config.get("dynamic_code_enabled"))

        control_outputs: list[BlockRuntimeOutput] = []
        logs: list[str] = []
        code_output = self._find_code_output(context.output_ports, normalized_config)
        if dynamic_code_enabled and code_output is not None:
            control_outputs.append(
                BlockRuntimeOutput(
                    port_id=int(getattr(code_output, "id", 0) or 0),
                    port_name=str(getattr(code_output, "name", "") or ""),
                    value=effective_script,
                    content_type=CODE_PYTHON,
                    metadata={
                        "python_code_override_used": code_override_used,
                        "python_code_override_input": code_override_label,
                    },
                )
            )
            logs.append(
                f"[python-code] {context.node_id}.{getattr(code_output, 'name', '') or getattr(code_output, 'id', '')} <= code effectif."
            )
        if code_override_used:
            logs.append(f"[python-code] {context.node_id}: script remplace par @{code_override_label}.")

        execution = self.execute(
            root_dir=context.root_dir,
            config=effective_config,
            inputs=self._named_inputs(context, normalized_config),
            work_dir=context.run_dir,
        )

        stdout = str(execution.get("stdout") or "")
        stderr = str(execution.get("stderr") or "")
        logs.extend(f"[python-stdout] {line}" for line in stdout.splitlines())
        logs.extend(f"[python-stderr] {line}" for line in stderr.splitlines())

        status = str(execution.get("status") or "failed")
        exit_code = int(execution.get("exit_code") or 0)
        if status != "success" or exit_code != 0:
            error = str(execution.get("error") or stderr or stdout or "Script Python en echec.")
            logs.append(f"[python-error] {context.node_id}: {error}")
            return BlockRuntimeResult(
                status="failed",
                outputs=control_outputs,
                logs=logs,
                error=error,
                exit_code=exit_code or 1,
                last_message=error,
                worker_received=error,
                metadata={
                    "stdout": stdout,
                    "stderr": stderr,
                    "python_code_override_used": code_override_used,
                    "python_code_override_input": code_override_label,
                },
            )

        raw_outputs = execution.get("outputs") if isinstance(execution.get("outputs"), dict) else {}
        output_ports_by_name = {
            str(getattr(port, "name", "") or "").strip(): port
            for port in context.output_ports
            if str(getattr(port, "name", "") or "").strip() and not self._is_code_output(port)
        }
        outputs = list(control_outputs)
        last_message = ""
        for output_name, raw_value in {str(key): value for key, value in raw_outputs.items()}.items():
            port = output_ports_by_name.get(output_name)
            if port is None:
                logs.append(f"[python-warn] {context.node_id}: output inconnu '{output_name}' ignore.")
                continue
            value = self.serialize_output_value(raw_value)
            content_type = APPLICATION_JSON if isinstance(raw_value, (dict, list)) else TEXT_PLAIN
            outputs.append(
                BlockRuntimeOutput(
                    port_id=int(getattr(port, "id", 0) or 0),
                    port_name=str(getattr(port, "name", "") or ""),
                    value=value,
                    content_type=content_type,
                )
            )
            last_message = value

        logs.append(f"[done] Python {context.node_id}: {len(outputs)} output(s) emis.")
        return BlockRuntimeResult(
            status="success",
            outputs=outputs,
            logs=logs,
            last_message=last_message,
            worker_received=last_message or "-",
            metadata={
                "stdout": stdout,
                "stderr": stderr,
                "python_outputs": sorted(str(key) for key in raw_outputs),
                "python_code_override_used": code_override_used,
                "python_code_override_input": code_override_label,
            },
        )

    def _effective_script(self, context: BlockRuntimeContext, config: dict[str, Any]) -> tuple[str, bool, str]:
        """Provide internal PythonBlock behavior for `_effective_script`.

        Args:
            context: Generic runtime context injected by the execution engine.
            config: Raw or normalized block configuration.
        """
        configured_script = str(config.get("script") or "")
        if not bool(config.get("dynamic_code_enabled")):
            return configured_script, False, ""
        input_port = self._find_code_input(context.input_ports, config)
        if input_port is None:
            return configured_script, False, ""
        port_id_key = str(getattr(input_port, "id", "") or "")
        port_name = str(getattr(input_port, "name", "") or "").strip()
        override_script = str(
            context.input_value(port_name, port_id_key)
            if port_name
            else context.input_value(port_id_key)
        )
        if not override_script.strip():
            return configured_script, False, ""
        return override_script, True, port_name or port_id_key

    def _named_inputs(self, context: BlockRuntimeContext, config: dict[str, Any]) -> dict[str, str]:
        """Provide internal PythonBlock behavior for `_named_inputs`.

        Args:
            context: Generic runtime context injected by the execution engine.
            config: Raw or normalized block configuration.
        """
        values: dict[str, str] = {}
        for input_port in context.input_ports:
            if self._is_code_input(input_port):
                continue
            port_id = str(getattr(input_port, "id", "") or "")
            port_name = str(getattr(input_port, "name", "") or "").strip() or port_id
            values[port_name] = str(context.input_value(port_name, port_id) or "")
        return values

    def _find_code_input(self, input_ports: tuple[Any, ...], config: dict[str, Any]) -> Any | None:
        """Find a matching runtime or graph element for this block.

        Args:
            input_ports: Input ports value used by this block helper.
            config: Raw or normalized block configuration.
        """
        port_id = config.get("code_input_port_id")
        if port_id:
            for input_port in input_ports:
                if int(getattr(input_port, "id", 0) or 0) == int(port_id) and self._is_code_input(input_port):
                    return input_port
        return next((input_port for input_port in input_ports if self._is_code_input(input_port)), None)

    def _find_code_output(self, output_ports: tuple[Any, ...], config: dict[str, Any]) -> Any | None:
        """Find a matching runtime or graph element for this block.

        Args:
            output_ports: Output ports value used by this block helper.
            config: Raw or normalized block configuration.
        """
        port_id = config.get("code_output_port_id")
        if port_id:
            for output_port in output_ports:
                if int(getattr(output_port, "id", 0) or 0) == int(port_id) and self._is_code_output(output_port):
                    return output_port
        return next((output_port for output_port in output_ports if self._is_code_output(output_port)), None)

    def _is_code_input(self, port: Any) -> bool:
        """Return whether the provided value matches this block condition.

        Args:
            port: Serialized or runtime port definition.
        """
        return CODE_PYTHON in tuple(getattr(port, "accepts", ()) or ())

    def _is_code_output(self, port: Any) -> bool:
        """Return whether the provided value matches this block condition.

        Args:
            port: Serialized or runtime port definition.
        """
        return CODE_PYTHON in tuple(getattr(port, "emits", ()) or getattr(port, "accepts", ()) or ())

    def _normalize_timeout(self, raw_value: Any) -> int:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_value: Raw value received from configuration or runtime input.
        """
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = DEFAULT_TIMEOUT_SEC
        return max(1, min(3600, value))

    def _normalize_param_name(self, raw_value: Any) -> str:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_value: Raw value received from configuration or runtime input.
        """
        normalized = str(raw_value or "").strip().lower()
        normalized = re.sub(r"\s+", "_", normalized)
        normalized = re.sub(r"-+", "_", normalized)
        normalized = re.sub(r"[^a-z0-9_]", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if normalized and normalized[0].isdigit():
            normalized = f"_{normalized}"
        return normalized

    def _normalize_params(self, raw_params: Any) -> list[dict[str, str]]:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_params: Raw value received from configuration or runtime input.
        """
        if isinstance(raw_params, dict):
            iterable = [{"name": key, "value": value} for key, value in raw_params.items()]
        elif isinstance(raw_params, list):
            iterable = raw_params
        else:
            iterable = []

        normalized: list[dict[str, str]] = []
        used: set[str] = set()
        for index, raw_param in enumerate(iterable, start=1):
            if isinstance(raw_param, dict):
                raw_name = raw_param.get("name") or raw_param.get("key") or raw_param.get("id")
                raw_value = raw_param.get("value", "")
            else:
                raw_name = f"param_{index}"
                raw_value = raw_param

            base_name = self._normalize_param_name(raw_name) or f"param_{index}"
            name = base_name
            suffix = 2
            while name in used:
                name = f"{base_name}_{suffix}"
                suffix += 1
            used.add(name)
            normalized.append({"name": name, "value": "" if raw_value is None else str(raw_value)})

        return normalized

    def _params_dict(self, params: Any) -> dict[str, str]:
        """Provide internal PythonBlock behavior for `_params_dict`.

        Args:
            params: Additional action or runtime parameters.
        """
        return {item["name"]: item["value"] for item in self._normalize_params(params)}

    def _normalize_optional_port_id(self, raw_value: Any) -> int | None:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_value: Raw value received from configuration or runtime input.
        """
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _runner_source(self) -> str:
        """Provide internal PythonBlock behavior for `_runner_source`."""
        return """from __future__ import annotations

import inspect
import importlib.util
import json
import sys
import traceback


def main() -> int:
    script_path, inputs_path, params_path, outputs_path = sys.argv[1:5]
    with open(inputs_path, "r", encoding="utf-8") as file:
        inputs = json.load(file)
    with open(params_path, "r", encoding="utf-8") as file:
        params = json.load(file)
    outputs = {}

    spec = importlib.util.spec_from_file_location("bloxsmith_user_python_block", script_path)
    if spec is None or spec.loader is None:
        print("Impossible de charger le script Python du bloc.", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        traceback.print_exc()
        return 1

    run = getattr(module, "run", None)
    if not callable(run):
        print(
            "Le script Python doit definir une fonction callable: def run(inputs, outputs) "
            "ou def run(inputs, outputs, params).",
            file=sys.stderr,
        )
        return 2

    try:
        signature = inspect.signature(run)
        positional_params = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ]
        accepts_varargs = any(
            parameter.kind == parameter.VAR_POSITIONAL for parameter in signature.parameters.values()
        )
        if accepts_varargs or len(positional_params) >= 3:
            run(inputs, outputs, params)
        else:
            run(inputs, outputs)
    except Exception:
        traceback.print_exc()
        return 1

    if not isinstance(outputs, dict):
        print("Le parametre outputs doit rester un dictionnaire.", file=sys.stderr)
        return 2

    with open(outputs_path, "w", encoding="utf-8") as file:
        json.dump(outputs, file, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
