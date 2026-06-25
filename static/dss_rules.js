(() => {
  "use strict";

  const API = {
    rules: "/api/dss/rules",
    evaluate: "/api/dss/rules/evaluate",
    criteria: "/api/dss/criteria?include_inactive=false",
  };

  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
      return "—";
    }

    return new Intl.NumberFormat("uk-UA", {
      maximumFractionDigits: 6,
    }).format(number);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });

    let payload;

    try {
      payload = await response.json();
    } catch {
      throw new Error(
        `Сервер повернув некоректну відповідь (${response.status}).`
      );
    }

    if (!response.ok || payload.success === false) {
      throw new Error(
        payload.message || `Помилка запиту: HTTP ${response.status}.`
      );
    }

    return payload.data ?? payload;
  }

  function getRulesPanel() {
    return (
      byId("panel-rules") ||
      document.querySelector('[data-panel="rules"]')
    );
  }

  function buildInterface() {
    const panel = getRulesPanel();

    if (!panel || byId("dss-ifthen-module")) {
      return;
    }

    const module = document.createElement("section");
    module.id = "dss-ifthen-module";
    module.className = "dss-ifthen-module";
    module.innerHTML = `
      <div class="dss-ifthen-heading">
        <div>
          <span class="dss-ifthen-kicker">Логічне керування рішенням</span>
          <h3>Правила IF–THEN</h3>
          <p>
            Правила можуть відхиляти альтернативи або коригувати
            їх інтегральні оцінки штрафом чи бонусом.
          </p>
        </div>
        <span id="dss-ifthen-status" class="dss-ifthen-status">
          Завантаження
        </span>
      </div>

      <div id="dss-ifthen-message"
           class="dss-ifthen-message"
           hidden></div>

      <article class="dss-ifthen-card">
        <h4>Нове правило</h4>
        <div class="dss-ifthen-form">
          <label>
            Назва
            <input id="dss-rule-name"
                   type="text"
                   placeholder="Наприклад: Висока ціна">
          </label>

          <label>
            Критерій
            <select id="dss-rule-criterion"></select>
          </label>

          <label>
            Оператор
            <select id="dss-rule-operator">
              <option value="<">&lt;</option>
              <option value="<=">&le;</option>
              <option value="=">=</option>
              <option value=">=">&ge;</option>
              <option value=">">&gt;</option>
            </select>
          </label>

          <label>
            Значення
            <input id="dss-rule-condition"
                   type="number"
                   step="any"
                   placeholder="7">
          </label>

          <label>
            Дія
            <select id="dss-rule-action">
              <option value="reject">Відхилити альтернативу</option>
              <option value="penalty">Зменшити оцінку</option>
              <option value="bonus">Збільшити оцінку</option>
            </select>
          </label>

          <label>
            Коригування, 0–1
            <input id="dss-rule-action-value"
                   type="number"
                   min="0"
                   max="1"
                   step="0.01"
                   value="0">
          </label>

          <label class="dss-ifthen-wide">
            Пояснення
            <input id="dss-rule-message"
                   type="text"
                   placeholder="Текст, який буде показано в результаті">
          </label>

          <label>
            Пріоритет
            <input id="dss-rule-priority"
                   type="number"
                   step="1"
                   value="100">
          </label>
        </div>

        <button type="button"
                id="dss-rule-create-button"
                class="dss-ifthen-primary">
          Додати правило
        </button>
      </article>

      <article class="dss-ifthen-card">
        <div class="dss-ifthen-card-title">
          <div>
            <h4>Збережені правила</h4>
            <p>Правила виконуються за зростанням пріоритету.</p>
          </div>
          <button type="button"
                  id="dss-rule-evaluate-button"
                  class="dss-ifthen-primary">
            Застосувати до матриці
          </button>
        </div>

        <div class="dss-ifthen-table-wrap">
          <table class="dss-ifthen-table">
            <thead>
              <tr>
                <th>IF</th>
                <th>THEN</th>
                <th>Пояснення</th>
                <th>Стан</th>
                <th>Дії</th>
              </tr>
            </thead>
            <tbody id="dss-rules-body"></tbody>
          </table>
        </div>
      </article>

      <article class="dss-ifthen-card">
        <div class="dss-ifthen-card-title">
          <div>
            <h4>Спрацювання правил</h4>
            <p>
              Тут показано, які правила вплинули на кожну альтернативу.
            </p>
          </div>
          <strong id="dss-rule-summary">Ще не перевірено</strong>
        </div>

        <div class="dss-ifthen-table-wrap">
          <table class="dss-ifthen-table">
            <thead>
              <tr>
                <th>Альтернатива</th>
                <th>Правило</th>
                <th>Фактичне значення</th>
                <th>Дія</th>
                <th>Результат</th>
              </tr>
            </thead>
            <tbody id="dss-rule-events-body">
              <tr>
                <td colspan="5" class="dss-ifthen-empty">
                  Натисніть «Застосувати до матриці».
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    `;

    const voting = byId("dss-voting-module");

    if (voting?.parentElement === panel) {
      panel.insertBefore(module, voting);
    } else {
      panel.appendChild(module);
    }
  }

  function showMessage(message, type = "info") {
    const box = byId("dss-ifthen-message");

    if (!box) {
      return;
    }

    box.textContent = message;
    box.dataset.type = type;
    box.hidden = false;
  }

  function setStatus(message, type = "idle") {
    const status = byId("dss-ifthen-status");

    if (!status) {
      return;
    }

    status.textContent = message;
    status.dataset.type = type;
  }

  function setButtonState(button, loading, loadingText, normalText) {
    if (!button) {
      return;
    }

    button.disabled = loading;
    button.textContent = loading ? loadingText : normalText;
  }

  function actionText(rule) {
    if (rule.action_type === "reject") {
      return "Відхилити";
    }

    const percent = formatNumber(Number(rule.action_value) * 100);

    if (rule.action_type === "penalty") {
      return `Штраф ${percent}%`;
    }

    return `Бонус ${percent}%`;
  }

  async function loadCriteria() {
    const criteria = await requestJson(API.criteria);
    const select = byId("dss-rule-criterion");

    if (!select) {
      return;
    }

    select.innerHTML = criteria
      .map(
        (criterion) => `
          <option value="${criterion.id}">
            ${escapeHtml(criterion.name)}
          </option>
        `
      )
      .join("");
  }

  function renderRules(rules) {
    const body = byId("dss-rules-body");

    if (!body) {
      return;
    }

    if (!rules.length) {
      body.innerHTML = `
        <tr>
          <td colspan="5" class="dss-ifthen-empty">
            Правила відсутні.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = rules
      .map(
        (rule) => `
          <tr>
            <td>
              <strong>${escapeHtml(rule.criterion_name)}</strong>
              ${escapeHtml(rule.operator)}
              ${formatNumber(rule.condition_value)}
            </td>
            <td>${escapeHtml(actionText(rule))}</td>
            <td>${escapeHtml(rule.message)}</td>
            <td>
              <span class="dss-ifthen-badge"
                    data-active="${rule.is_active}">
                ${rule.is_active ? "Активне" : "Вимкнене"}
              </span>
            </td>
            <td class="dss-ifthen-actions">
              <button type="button"
                      data-rule-toggle="${rule.id}"
                      data-rule-active="${rule.is_active}">
                ${rule.is_active ? "Вимкнути" : "Увімкнути"}
              </button>
              <button type="button"
                      data-rule-delete="${rule.id}"
                      class="danger">
                Видалити
              </button>
            </td>
          </tr>
        `
      )
      .join("");

    body.querySelectorAll("[data-rule-toggle]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.ruleToggle;
        const active = button.dataset.ruleActive === "true";

        try {
          await requestJson(`${API.rules}/${id}`, {
            method: "PUT",
            body: JSON.stringify({ is_active: !active }),
          });
          showMessage("Стан правила оновлено.", "success");
          await loadRules();
        } catch (error) {
          showMessage(error.message, "error");
        }
      });
    });

    body.querySelectorAll("[data-rule-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.ruleDelete;

        if (!window.confirm("Видалити це правило?")) {
          return;
        }

        try {
          await requestJson(`${API.rules}/${id}`, {
            method: "DELETE",
          });
          showMessage("Правило видалено.", "success");
          await loadRules();
        } catch (error) {
          showMessage(error.message, "error");
        }
      });
    });
  }

  async function loadRules() {
    const rules = await requestJson(API.rules);
    renderRules(rules);
    setStatus(`${rules.filter((rule) => rule.is_active).length} активні`, "success");
    return rules;
  }

  function formPayload() {
    return {
      name: byId("dss-rule-name")?.value.trim(),
      criterion_id: Number(byId("dss-rule-criterion")?.value),
      operator: byId("dss-rule-operator")?.value,
      condition_value: Number(byId("dss-rule-condition")?.value),
      action_type: byId("dss-rule-action")?.value,
      action_value: Number(byId("dss-rule-action-value")?.value || 0),
      message: byId("dss-rule-message")?.value.trim(),
      priority: Number(byId("dss-rule-priority")?.value || 100),
      is_active: true,
    };
  }

  async function createRule() {
    const button = byId("dss-rule-create-button");
    const payload = formPayload();

    if (!payload.name || !Number.isFinite(payload.condition_value)) {
      showMessage(
        "Заповніть назву правила та числове значення умови.",
        "error"
      );
      return;
    }

    setButtonState(button, true, "Збереження...", "Додати правило");

    try {
      await requestJson(API.rules, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showMessage("Нове правило IF–THEN створено.", "success");
      byId("dss-rule-name").value = "";
      byId("dss-rule-condition").value = "";
      byId("dss-rule-message").value = "";
      await loadRules();
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      setButtonState(button, false, "Збереження...", "Додати правило");
    }
  }

  function renderEvaluation(data) {
    const body = byId("dss-rule-events-body");
    const summary = byId("dss-rule-summary");

    if (!body) {
      return;
    }

    const rows = [];

    for (const alternative of data.alternatives ?? []) {
      if (!alternative.events?.length) {
        rows.push(`
          <tr>
            <td>${escapeHtml(alternative.alternative)}</td>
            <td colspan="3">Жодне правило не спрацювало</td>
            <td>Без змін</td>
          </tr>
        `);
        continue;
      }

      for (const event of alternative.events) {
        rows.push(`
          <tr>
            <td>${escapeHtml(alternative.alternative)}</td>
            <td>${escapeHtml(event.rule)}</td>
            <td>
              ${formatNumber(event.actual_value)}
              ${escapeHtml(event.operator)}
              ${formatNumber(event.condition_value)}
            </td>
            <td>${escapeHtml(event.action_label)}</td>
            <td>${escapeHtml(event.message)}</td>
          </tr>
        `);
      }
    }

    body.innerHTML = rows.join("");

    if (summary) {
      summary.textContent =
        `${data.triggered_events_count} спрацювань, ` +
        `${data.rejected_alternatives_count} відхилено`;
    }
  }

  async function evaluateRules() {
    const button = byId("dss-rule-evaluate-button");

    setButtonState(
      button,
      true,
      "Перевірка...",
      "Застосувати до матриці"
    );

    try {
      const data = await requestJson(API.evaluate, {
        method: "POST",
      });
      renderEvaluation(data);
      showMessage(
        "Правила перевірено. Вони автоматично враховуються у рейтингу.",
        "success"
      );
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      setButtonState(
        button,
        false,
        "Перевірка...",
        "Застосувати до матриці"
      );
    }
  }

  function updateActionField() {
    const action = byId("dss-rule-action")?.value;
    const input = byId("dss-rule-action-value");

    if (!input) {
      return;
    }

    input.disabled = action === "reject";

    if (action === "reject") {
      input.value = "0";
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    buildInterface();

    byId("dss-rule-create-button")?.addEventListener(
      "click",
      createRule
    );
    byId("dss-rule-evaluate-button")?.addEventListener(
      "click",
      evaluateRules
    );
    byId("dss-rule-action")?.addEventListener(
      "change",
      updateActionField
    );

    updateActionField();

    try {
      await Promise.all([
        loadCriteria(),
        loadRules(),
      ]);
    } catch (error) {
      setStatus("Помилка", "error");
      showMessage(error.message, "error");
    }
  });
})();
