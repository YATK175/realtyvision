(() => {
  "use strict";

  const API = {
    status: "/api/dss/status",
    alternatives: "/api/dss/alternatives",
    criteria: "/api/dss/criteria?include_inactive=false",
    matrix: "/api/dss/matrix",
    scores: "/api/dss/scores",
  };

  const state = {
    alternatives: [],
    criteria: [],
    values: {},
    validation: {},
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value, maximumFractionDigits = 2) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }

    const number = Number(value);

    if (!Number.isFinite(number)) {
      return escapeHtml(value);
    }

    return new Intl.NumberFormat("uk-UA", {
      maximumFractionDigits,
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
      throw new Error(`Сервер повернув некоректну відповідь (${response.status}).`);
    }

    if (!response.ok || payload.success === false) {
      throw new Error(
        payload.message || `Помилка запиту: HTTP ${response.status}.`
      );
    }

    return payload.data ?? payload;
  }

  function showMessage(message, type = "info") {
    const container = byId("dss-api-message");

    if (!container) {
      console[type === "error" ? "error" : "log"](message);
      return;
    }

    container.textContent = message;
    container.dataset.type = type;
    container.hidden = false;

    window.clearTimeout(showMessage.timeoutId);
    showMessage.timeoutId = window.setTimeout(() => {
      container.hidden = true;
    }, 4500);
  }

  function setLoading(isLoading) {
    const refreshButton = document.querySelector("[data-dss-refresh]");

    if (refreshButton) {
      refreshButton.disabled = isLoading;
      refreshButton.textContent = isLoading
        ? "Завантаження..."
        : "Оновити дані";
    }
  }

  function renderStatus(status) {
    const labBadge = byId("dss-lab-badge");
    const moduleStatus = byId("dss-module-status");

    if (labBadge) {
      labBadge.textContent = `Лабораторна робота №${status.laboratory ?? 2}`;
    }

    if (moduleStatus) {
      moduleStatus.textContent = "Модуль СППР активний";
    }
  }

  function renderAlternatives() {
    const body = byId("alternatives-table-body");

    if (!body) {
      return;
    }

    if (state.alternatives.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="4" class="dss-empty">
            Альтернативи ще не додані.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = state.alternatives
      .map(
        (item) => `
          <tr>
            <td>${item.id}</td>
            <td>${escapeHtml(item.name)}</td>
            <td>${escapeHtml(item.address || "—")}</td>
            <td>${escapeHtml(item.description || "—")}</td>
          </tr>
        `
      )
      .join("");
  }

  function renderCriteria() {
    const body = byId("criteria-table-body");

    if (!body) {
      return;
    }

    if (state.criteria.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="7" class="dss-empty">
            Критерії ще не додані.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = state.criteria
      .map(
        (item) => `
          <tr>
            <td>${item.id}</td>
            <td>${escapeHtml(item.name)}</td>
            <td>
              ${item.criterion_type === "maximize" ? "Максимізація" : "Мінімізація"}
            </td>
            <td>${formatNumber(item.weight, 4)}</td>
            <td>${escapeHtml(item.unit || "—")}</td>
            <td>
              ${item.threshold_operator
                ? `${escapeHtml(item.threshold_operator)} ${formatNumber(item.threshold_value)}`
                : "—"}
            </td>
            <td>${item.is_active ? "Активний" : "Неактивний"}</td>
          </tr>
        `
      )
      .join("");
  }

  function scoreInput(alternative, criterion) {
    const saved = state.values[String(alternative.id)]?.[String(criterion.id)];
    const value = saved?.value ?? "";
    const min = criterion.scale_min ?? "";
    const max = criterion.scale_max ?? "";

    return `
      <input
        class="dss-score-input"
        type="number"
        step="any"
        value="${escapeHtml(value)}"
        min="${escapeHtml(min)}"
        max="${escapeHtml(max)}"
        data-alternative-id="${alternative.id}"
        data-criterion-id="${criterion.id}"
        aria-label="${escapeHtml(`${alternative.name}: ${criterion.name}`)}"
      >
    `;
  }

  function renderMatrix() {
    const head = byId("matrix-table-head");
    const body = byId("matrix-table-body");

    if (!head || !body) {
      return;
    }

    head.innerHTML = `
      <tr>
        <th>Альтернатива</th>
        ${state.criteria
          .map(
            (criterion) => `
              <th>
                ${escapeHtml(criterion.name)}
                ${criterion.unit ? `<small>(${escapeHtml(criterion.unit)})</small>` : ""}
              </th>
            `
          )
          .join("")}
      </tr>
    `;

    if (state.alternatives.length === 0 || state.criteria.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="${Math.max(1, state.criteria.length + 1)}" class="dss-empty">
            Для матриці потрібні альтернативи та активні критерії.
          </td>
        </tr>
      `;
      renderMatrixValidation();
      return;
    }

    body.innerHTML = state.alternatives
      .map(
        (alternative) => `
          <tr>
            <th>${escapeHtml(alternative.name)}</th>
            ${state.criteria
              .map(
                (criterion) => `
                  <td>${scoreInput(alternative, criterion)}</td>
                `
              )
              .join("")}
          </tr>
        `
      )
      .join("");

    body.querySelectorAll(".dss-score-input").forEach((input) => {
      input.addEventListener("change", saveScoreFromInput);
    });

    renderMatrixValidation();
  }

  function renderMatrixValidation() {
    const container = byId("matrix-validation");

    if (!container) {
      return;
    }

    const validation = state.validation || {};
    const complete = Boolean(validation.matrix_is_complete);
    const weightsOk = Boolean(validation.weights_are_normalized);

    container.innerHTML = `
      <span class="${weightsOk ? "dss-ok" : "dss-warning"}">
        Сума ваг: ${formatNumber(validation.weight_sum ?? 0, 4)}
      </span>
      <span class="${complete ? "dss-ok" : "dss-warning"}">
        Матриця: ${complete ? "заповнена" : "є пропущені значення"}
      </span>
      <span>
        Збережено: ${validation.saved_values_count ?? 0}
        із ${validation.expected_values_count ?? 0}
      </span>
    `;
  }

  async function saveScoreFromInput(event) {
    const input = event.currentTarget;
    const previousValue =
      state.values[input.dataset.alternativeId]?.[input.dataset.criterionId]?.value ?? "";

    if (input.value === "") {
      input.value = previousValue;
      showMessage("Порожнє значення не збережено.", "error");
      return;
    }

    input.disabled = true;

    try {
      await requestJson(API.scores, {
        method: "PUT",
        body: JSON.stringify({
          alternative_id: Number(input.dataset.alternativeId),
          criterion_id: Number(input.dataset.criterionId),
          value: Number(input.value),
          source: "manual",
        }),
      });

      input.classList.remove("dss-score-error");
      input.classList.add("dss-score-saved");
      showMessage("Оцінку успішно збережено.", "success");

      await loadMatrixOnly();
    } catch (error) {
      input.value = previousValue;
      input.classList.add("dss-score-error");
      showMessage(error.message, "error");
    } finally {
      input.disabled = false;

      window.setTimeout(() => {
        input.classList.remove("dss-score-saved");
      }, 1200);
    }
  }

  async function loadMatrixOnly() {
    const matrix = await requestJson(API.matrix);

    state.alternatives = matrix.alternatives ?? [];
    state.criteria = matrix.criteria ?? [];
    state.values = matrix.values ?? {};
    state.validation = matrix.validation ?? {};

    renderAlternatives();
    renderCriteria();
    renderMatrix();
  }

  async function loadAll() {
    setLoading(true);

    try {
      const [status, matrix] = await Promise.all([
        requestJson(API.status),
        requestJson(API.matrix),
      ]);

      renderStatus(status);

      state.alternatives = matrix.alternatives ?? [];
      state.criteria = matrix.criteria ?? [];
      state.values = matrix.values ?? {};
      state.validation = matrix.validation ?? {};

      renderAlternatives();
      renderCriteria();
      renderMatrix();

      showMessage("Дані СППР завантажено з SQLite.", "success");
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      setLoading(false);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("[data-dss-refresh]")?.addEventListener(
      "click",
      loadAll
    );

    loadAll();
  });

  window.RealtyVisionDSS = {
    refresh: loadAll,
    state,
  };
})();
