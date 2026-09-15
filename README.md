# Python Block

<!-- block-metadata:start -->
[![Block version: 0.1.1](https://img.shields.io/badge/block-0.1.1-blue)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


## Role

`python` executes a user-provided Python `run(inputs, outputs, params)` function and emits values assigned to output names.

## Files

- `block.py`: config normalization, script execution, dynamic-code support, timeout handling, and output serialization.
- `model.json`: default script, timeout, executable, params, and dynamic-code config.
- `inspector_panel.html`: Python inspector UI.
- `block_modal.html`: tabbed Python modal with a dedicated code editor.
- `assets/css/block_modal.css`: Python modal sizing, dark code editor, line-number gutter, and diagnostics styling.
- `assets/js/block_modal.js`: Python modal tabs, code counter, line numbers, indentation, Ctrl+Enter shortcut, syntax check, and Beautiful Python action.
- `node_card.html`: block-owned canvas card body.

## Ports

- Inputs:
  - `in` (`id: 1`): optional `message/*`.
- Outputs:
  - `out` (`id: 1`): emits `message/*`.

Additional code input/output ports can be selected through config when dynamic code is enabled.

## Configuration

- `script`: Python source containing a `run` function.
- `timeout_sec`: execution timeout.
- `python_executable`: interpreter command.
- `params`: named parameter list exposed to the script.
- `dynamic_code_enabled`: allows runtime code injection through a selected input port.
- `code_input_port_id`: optional input carrying dynamic Python code.
- `code_output_port_id`: optional output carrying the effective code.

## Runtime Behavior

`execute_runtime()` prepares named inputs and params, resolves the effective script, runs it in an isolated subprocess-style runner, serializes output values, and emits matching output ports. A separate process is not an OS security sandbox.

In Active Runtime, runtime-mutable edits such as `script`, timeout, interpreter,
params, and dynamic-code options can be saved while a run is loaded. The worker
keeps the snapshot used by any execution already in progress; the next activation
hot-loads the refreshed config only if the topology and ports are unchanged.
Topology edits still require stopping the active run first.

## UI Behavior

### Release UI contract (0.1.1)

Install or link this package as `python@0.1.1`. `model.json.ui_assets` declares
the modal's CSS and ES-module entrypoint; Python hooks no longer list assets.
The module exports `mount` and never registers an unversioned browser global.
Styles are scoped to this exact release so another Python version cannot replace
its layout. Closing or replacing the modal detaches its editor listeners.

The code counter initializes from the actual saved script. Tabs support arrow
keys, Home and End with associated panels; the editor has an accessible label.
Small screens use compact tabs and actions with an internally scrolling editor.
Syntax diagnostics and Close/Apply remain reachable.

Existing `0.1.0` tags and blueprint references are not rewritten. Upgrade a
blueprint's explicit block version after installing/reloading this release;
unversioned bundled UI loading is not a fallback for these ES modules.

The inspector shows a read-only script preview, timeout/interpreter config,
params, and dynamic-code settings. Script editing is intentionally handled only
by the block modal. Editable inspector fields use the generic block UI
field-binding contract. Timeout, params, and dynamic-code settings are kept
pending while edited and are persisted through the GraphController only when the
user clicks **Apply**.

The block modal is owned by the Python block. It opens on a large, Codex-style
layout with a left tab rail and three sections:

- `Code`: large monospace script editor bound to `config.script`, with line and
  character count, dark theme, line numbers, API reference hints, Tab
  indentation, Ctrl+Enter apply shortcut, a conservative `Beautiful Python`
  formatter, and syntax diagnostics.
- **Attributes**: title, timeout, interpreter, dynamic-code options, and params
  JSON bound through the generic modal field contract.
- **Ports & state**: read-only port and latest runtime state information.

## Editor Display

The canvas card is rendered by this block through `node_card.html`. It exposes script size, parameter count, and timeout while the shared editor shell keeps ports, dragging, status, and graph links generic.

## Modal

`block_modal.html` is owned by this block and rendered by the generic modal contract. It declares `data-block-runtime-refresh="autonomous"` because the code editor, tabs, diagnostics, focus, scroll, and local draft script must stay stable while runtime polling updates node cards. It keeps code editing separate from attributes while persisting supported title/config fields through generic bindings. Syntax checks and the conservative formatter are block-owned UI actions handled by `block.py`, so no Python-specific behavior is added to the shared modal framework.

## Maintenance Notes

`F8.19_python_release_ui.py` installs the current package and links a synthetic
second version through the real framework. Chromium verifies tabs, counters,
validation/formatting, saved drafts, repeated opening, release isolation and
desktop/mobile layouts. The same managed and linked code is executed in
`centralized` and `zeromq_active`. The synthetic version is only an isolation
fixture, not a published release or an additional compatibility claim.

Preserve validation around dynamic code. Do not bypass `python_validation.py` or move Python-block-specific execution rules into the orchestrator. The isolated runner loads user scripts under the internal module name `bloxsmith_user_python_block` so tracebacks and module identity follow the BloxSmith package name.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. The outer harness is a **bundled-block test installation**; the release-specific suites described above additionally install and link this package through the real framework. Evidence covers those explicit cases, not every distribution format, browser/OS or live provider. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.
