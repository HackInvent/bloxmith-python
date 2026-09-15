/**
 * Role: Mounts the Python block modal frontend asset.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-05-17
 */


const mounts = new WeakMap();

/**
 * Return Python modal tabs in DOM order.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @returns {HTMLElement[]} Tab buttons controlled by this asset.
 */
function tabElements(root) {
  return Array.from(root.querySelectorAll("[data-python-modal-tab]"));
}

/**
 * Return Python modal panels in DOM order.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @returns {HTMLElement[]} Panels associated with modal tabs.
 */
function panelElements(root) {
  return Array.from(root.querySelectorAll("[data-python-modal-panel]"));
}

/**
 * Update the script size summary displayed above the editor.
 *
 * @param {HTMLTextAreaElement} textarea - Python source textarea.
 * @param {HTMLElement} count - Counter element.
 */
function updateCodeCount(textarea, count) {
  if (!textarea || !count) {
    return;
  }
  const value = String(textarea.value || "");
  const lineCount = value ? value.replace(/\r\n?/g, "\n").split("\n").length : 1;
  count.textContent = `${lineCount} ligne${lineCount > 1 ? "s" : ""} · ${value.length} caractère${value.length > 1 ? "s" : ""}`;
}

/**
 * Keep the dark editor gutter aligned with the textarea line count.
 *
 * @param {HTMLTextAreaElement} textarea - Python source textarea.
 * @param {HTMLElement} gutter - Pre element that displays line numbers.
 */
function updateLineNumbers(textarea, gutter) {
  if (!textarea || !gutter) {
    return;
  }
  const lineCount = Math.max(1, String(textarea.value || "").replace(/\r\n?/g, "\n").split("\n").length);
  gutter.textContent = Array.from({ length: lineCount }, (_, index) => String(index + 1)).join("\n");
}

/**
 * Mirror the textarea vertical scroll position in the line-number gutter.
 *
 * @param {HTMLTextAreaElement} textarea - Python source textarea.
 * @param {HTMLElement} gutter - Line-number gutter.
 */
function syncGutterScroll(textarea, gutter) {
  if (!textarea || !gutter) {
    return;
  }
  gutter.scrollTop = textarea.scrollTop;
}

/**
 * Extract diagnostics from a block UI action response.
 *
 * @param {object} result - UI action result.
 * @returns {Array<object>} Diagnostics returned by the Python block.
 */
function diagnosticsFromResult(result) {
  const diagnostics = Array.isArray(result?.diagnostics) ? result.diagnostics : [];
  return diagnostics.filter((item) => item && typeof item === "object");
}

/**
 * Render syntax diagnostics in the Python-owned modal feedback area.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @param {object} result - UI action result with diagnostics.
 * @param {object} options - Rendering options.
 */
function renderDiagnostics(root, result, { fallback = "Syntaxe vérifiée." } = {}) {
  const feedback = root.querySelector("[data-python-editor-feedback]");
  if (!feedback) {
    return;
  }
  const diagnostics = diagnosticsFromResult(result);
  const hasError = diagnostics.some((item) => item.severity === "error");
  const hasWarning = diagnostics.some((item) => item.severity === "warning");
  feedback.classList.toggle("is-ok", !hasError && !hasWarning);
  feedback.classList.toggle("is-warning", !hasError && hasWarning);
  feedback.classList.toggle("is-error", hasError);
  if (!diagnostics.length) {
    feedback.textContent = fallback;
    return;
  }
  const items = diagnostics.map((item) => {
    const line = item.line ? `L${item.line}${item.column ? `:${item.column}` : ""} · ` : "";
    const severity = item.severity === "error" ? "Erreur" : "Avertissement";
    return `<li>${severity} · ${line}${escapeHtml(item.message || "Diagnostic Python.")}</li>`;
  }).join("");
  feedback.innerHTML = `<ul class="python-editor-diagnostics">${items}</ul>`;
}

/**
 * Show a transient pending state while an editor action is running.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @param {string} message - Pending message.
 */
function setFeedbackPending(root, message) {
  const feedback = root.querySelector("[data-python-editor-feedback]");
  if (!feedback) {
    return;
  }
  feedback.classList.remove("is-ok", "is-warning", "is-error");
  feedback.textContent = message;
}

/**
 * Escape diagnostic text before injecting it into the feedback list.
 *
 * @param {string} value - Raw diagnostic text.
 * @returns {string} HTML-safe text.
 */
function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Insert four spaces at the current caret position for Python indentation.
 *
 * @param {HTMLTextAreaElement} textarea - Python source textarea.
 */
function insertIndent(textarea) {
  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? start;
  textarea.setRangeText("    ", start, end, "end");
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

/**
 * Activate one Python modal tab and expose its matching panel.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @param {HTMLElement} tab - Tab element to activate.
 * @param {object} options - Activation options.
 * @param {boolean} options.focus - Whether keyboard focus should move to the tab.
 */
function activateTab(root, tab, { focus = false } = {}) {
  if (!(tab instanceof HTMLElement)) {
    return;
  }
  const tabId = String(tab.dataset.pythonTabId || "");
  for (const candidate of tabElements(root)) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", selected ? "true" : "false");
    candidate.tabIndex = selected ? 0 : -1;
  }
  for (const panel of panelElements(root)) {
    panel.hidden = String(panel.dataset.pythonTabId || "") !== tabId;
  }
  if (focus) {
    tab.focus();
  } else if (tabId === "code") {
    root.querySelector("[data-python-code-editor]")?.focus();
  }
}

/**
 * Move selection to a neighboring Python modal tab.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @param {HTMLElement} current - Currently focused tab.
 * @param {number} direction - Relative movement, usually -1 or 1.
 */
function moveTab(root, current, direction) {
  const tabs = tabElements(root);
  const index = tabs.indexOf(current);
  if (index < 0 || !tabs.length) {
    return;
  }
  const nextIndex = (index + direction + tabs.length) % tabs.length;
  activateTab(root, tabs[nextIndex], { focus: true });
}

/**
 * Bind Python modal tabs and code-editor keyboard shortcuts.
 *
 * @param {HTMLElement} root - Mounted Python modal root.
 * @param {object} api - Generic block UI API provided by the modal host.
 */
export function mount(root, api = {}) {
  mounts.get(root)?.();
  const controller = new AbortController();
  const listen = (element, type, handler) => element?.addEventListener(type, handler, { signal: controller.signal });
  const observer = new MutationObserver(() => { if (!root.isConnected) cleanup(); });
  let focusTimer;
  /** Detach this editor only; pending requests cannot update a replacement surface. */
  function cleanup() {
    if (controller.signal.aborted) return;
    controller.abort();
    observer.disconnect();
    window.clearTimeout(focusTimer);
    mounts.delete(root);
  }
  mounts.set(root, cleanup);
  observer.observe(document.body, { childList: true, subtree: true });
  const textarea = root.querySelector("[data-python-code-editor]");
  const count = root.querySelector("[data-python-code-count]");
  const gutter = root.querySelector("[data-python-line-numbers]");
  const applyButton = root.querySelector("[data-block-apply]");
  for (const tab of tabElements(root)) {
    const panel = panelElements(root).find(item => item.dataset.pythonTabId === tab.dataset.pythonTabId);
    if (!panel) continue;
    tab.id = `${root.dataset.nodeId}-python-tab-${tab.dataset.pythonTabId}`;
    panel.id = `${tab.id}-panel`;
    tab.setAttribute("aria-controls", panel.id);
    panel.setAttribute("aria-labelledby", tab.id);
  }
  const selected = root.querySelector('[data-python-modal-tab][aria-selected="true"]')
    || root.querySelector("[data-python-modal-tab]");
  activateTab(root, selected);

  listen(root, "click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const tab = target?.closest("[data-python-modal-tab]");
    if (!tab || !root.contains(tab)) {
      return;
    }
    event.preventDefault();
    activateTab(root, tab, { focus: true });
  });

  listen(root, "click", async (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const actionButton = target?.closest("[data-python-editor-action]");
    if (!(actionButton instanceof HTMLButtonElement) || !root.contains(actionButton) || !textarea) {
      return;
    }
    event.preventDefault();
    const action = String(actionButton.dataset.pythonEditorAction || "");
    const previousDisabled = actionButton.disabled;
    actionButton.disabled = true;
    try {
      if (action === "check-syntax") {
        setFeedbackPending(root, "Vérification de la syntaxe Python...");
        const result = await api.applyAction?.("python_check_syntax", { script: textarea.value });
        if (controller.signal.aborted) return;
        renderDiagnostics(root, result, { fallback: "Syntaxe Python valide." });
      } else if (action === "beautify") {
        setFeedbackPending(root, "Mise en forme Python...");
        const result = await api.applyAction?.("python_beautify_script", { script: textarea.value });
        if (controller.signal.aborted) return;
        if (result?.script && result.script !== textarea.value) {
          textarea.value = result.script;
          textarea.dispatchEvent(new Event("input", { bubbles: true }));
        }
        renderDiagnostics(root, result, { fallback: "Script mis en forme et syntaxe valide." });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      renderDiagnostics(root, {
        ok: false,
        diagnostics: [{ severity: "error", message: error?.message || "Action Python impossible." }],
      });
    } finally {
      actionButton.disabled = previousDisabled;
    }
  });

  listen(root, "keydown", (event) => {
    const tab = event.target.closest("[data-python-modal-tab]");
    if (!tab || !root.contains(tab)) {
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveTab(root, tab, 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveTab(root, tab, -1);
    } else if (event.key === "Home") {
      event.preventDefault();
      activateTab(root, tabElements(root)[0], { focus: true });
    } else if (event.key === "End") {
      event.preventDefault();
      const tabs = tabElements(root);
      activateTab(root, tabs[tabs.length - 1], { focus: true });
    }
  });

  listen(textarea, "input", () => {
    updateCodeCount(textarea, count);
    updateLineNumbers(textarea, gutter);
    syncGutterScroll(textarea, gutter);
  });
  listen(textarea, "scroll", () => syncGutterScroll(textarea, gutter));
  listen(textarea, "keydown", (event) => {
    if (event.key === "Tab" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      insertIndent(textarea);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      applyButton?.click();
    }
  });

  updateCodeCount(textarea, count);
  updateLineNumbers(textarea, gutter);
  syncGutterScroll(textarea, gutter);
  focusTimer = window.setTimeout(() => textarea?.focus(), 0);
  return cleanup;
}
