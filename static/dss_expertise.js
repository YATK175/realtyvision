(() => {
  "use strict";

  const API = {
    importGoogleSheets: "/api/dss/import/google-sheets",
    expertScores: "/api/dss/expert-scores",
    consensus: "/api/dss/consensus",
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
      maximumFractionDigits: 3,
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

  function ensureMessageBox() {
    let box = byId("dss-expertise-message");

    if (box) {
      return box;
    }

    const panel = byId("panel-expertise");

    if (!panel) {
      return null;
    }

    box = document.createElement("div");
    box.id = "dss-expertise-message";
    box.className = "dss-results-message";
    box.hidden = true;

    const sectionTitle = panel.querySelector(".dss-section-title");
    sectionTitle?.insertAdjacentElement("afterend", box);

    return box;
  }

  function showMessage(message, type = "info") {
    const box = ensureMessageBox();

    if (!box) {
      console[type === "error" ? "error" : "log"](message);
      return;
    }

    box.textContent = message;
    box.dataset.type = type;
    box.hidden = false;
  }

  function setButtonState(button, loading, loadingText, normalText) {
    if (!button) {
      return;
    }

    button.disabled = loading;
    button.textContent = loading ? loadingText : normalText;
  }

  function groupRows(data) {
    const grouped = new Map();
    const criteria = Array.isArray(data.criteria) ? data.criteria : [];

    for (const score of data.scores ?? []) {
      const key = `${score.expert_id}:${score.alternative_id}`;

      if (!grouped.has(key)) {
        grouped.set(key, {
          expert: score.expert_name,
          alternative: score.alternative_name,
          values: {},
        });
      }

      grouped.get(key).values[score.criterion_name] = score.value;
    }

    return {
      criteria,
      rows: [...grouped.values()],
    };
  }

  function renderExpertScores(data) {
    const body = byId("expert-scores-table-body");

    if (!body) {
      return;
    }

    const table = body.closest("table");
    const head = table?.querySelector("thead");
    const { criteria, rows } = groupRows(data);

    if (head) {
      head.innerHTML = `
        <tr>
          <th>Експерт</th>
          <th>Альтернатива</th>
          ${criteria
            .map(
              (criterion) =>
                `<th>${escapeHtml(criterion)}</th>`
            )
            .join("")}
        </tr>
      `;
    }

    if (rows.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="${Math.max(2, criteria.length + 2)}" class="dss-empty">
            Експертні оцінки ще не імпортовані.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = rows
      .map(
        (row) => `
          <tr>
            <td>${escapeHtml(row.expert)}</td>
            <td>${escapeHtml(row.alternative)}</td>
            ${criteria
              .map(
                (criterion) =>
                  `<td>${formatNumber(row.values[criterion])}</td>`
              )
              .join("")}
          </tr>
        `
      )
      .join("");
  }

  async function loadExpertScores({ silent = false } = {}) {
    try {
      const data = await requestJson(API.expertScores);
      renderExpertScores(data);

      if (!silent && (data.scores?.length ?? 0) > 0) {
        showMessage(
          `Завантажено ${data.scores.length} експертних оцінок.`,
          "success"
        );
      }

      return data;
    } catch (error) {
      showMessage(error.message, "error");
      throw error;
    }
  }

  async function importGoogleSheets() {
    const input = byId("google-sheets-url");
    const button = byId("google-sheets-import-button");
    const url = String(input?.value ?? "").trim();

    if (!url) {
      showMessage("Вставте посилання на опубліковану Google Таблицю.", "error");
      input?.focus();
      return;
    }

    setButtonState(
      button,
      true,
      "Імпорт...",
      "Імпортувати оцінки"
    );

    try {
      const result = await requestJson(API.importGoogleSheets, {
        method: "POST",
        body: JSON.stringify({ url }),
      });

      showMessage(
        `Імпорт завершено: ${result.imported_rows} рядків, ` +
          `${result.imported_scores} оцінок, ` +
          `${result.experts_count} експерти.`,
        "success"
      );

      await loadExpertScores({ silent: true });
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      setButtonState(
        button,
        false,
        "Імпорт...",
        "Імпортувати оцінки"
      );
    }
  }

  async function calculateConsensus() {
    const select = byId("consensus-method");
    const button = byId("consensus-calculate-button");
    const method = String(select?.value ?? "arithmetic_mean");

    setButtonState(
      button,
      true,
      "Узгодження...",
      "Узгодити оцінки"
    );

    try {
      const result = await requestJson(API.consensus, {
        method: "POST",
        body: JSON.stringify({ method }),
      });

      showMessage(
        `Узгодження завершено. До матриці записано ` +
          `${result.groups_count} узгоджених значень.`,
        "success"
      );

      if (window.RealtyVisionDSS?.refresh) {
        await window.RealtyVisionDSS.refresh();
      }
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      setButtonState(
        button,
        false,
        "Узгодження...",
        "Узгодити оцінки"
      );
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    ensureMessageBox();

    byId("google-sheets-import-button")?.addEventListener(
      "click",
      importGoogleSheets
    );

    byId("consensus-calculate-button")?.addEventListener(
      "click",
      calculateConsensus
    );

    loadExpertScores({ silent: true });
  });
})();
