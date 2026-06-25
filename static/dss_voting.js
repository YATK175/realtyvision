(() => {
  "use strict";

  const API = {
    importVoting: "/api/dss/voting/import/google-sheets",
    listVoting: "/api/dss/voting",
    calculateVoting: "/api/dss/voting/calculate",
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

  function formatNumber(value, digits = 6) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
      return "—";
    }

    return new Intl.NumberFormat("uk-UA", {
      maximumFractionDigits: digits,
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

    if (!panel || byId("dss-voting-module")) {
      return;
    }

    const module = document.createElement("section");
    module.id = "dss-voting-module";
    module.className = "dss-voting-module";

    module.innerHTML = `
      <div class="dss-voting-heading">
        <div>
          <span class="dss-voting-kicker">Визначення ваг критеріїв</span>
          <h3>Голосування експертів</h3>
          <p>
            Імпортуйте ранжування критеріїв, оберіть метод голосування
            та застосуйте розраховані ваги до моделі СППР.
          </p>
        </div>
        <span class="dss-voting-status" id="dss-voting-status">
          Очікування даних
        </span>
      </div>

      <div id="dss-voting-message"
           class="dss-voting-message"
           hidden></div>

      <div class="dss-voting-grid">
        <article class="dss-voting-card">
          <h4>Імпорт із Google Sheets</h4>
          <label for="dss-voting-url">
            Посилання на опублікований CSV
          </label>
          <input
            id="dss-voting-url"
            type="url"
            placeholder="https://docs.google.com/spreadsheets/..."
            autocomplete="off"
          >
          <button
            type="button"
            id="dss-voting-import-button"
            class="dss-voting-primary"
          >
            Імпортувати голоси
          </button>
        </article>

        <article class="dss-voting-card">
          <h4>Розрахунок ваг</h4>
          <label for="dss-voting-method">
            Метод голосування
          </label>
          <select id="dss-voting-method">
            <option value="plurality">
              Відносна більшість
            </option>
            <option value="borda" selected>
              Метод Борда
            </option>
            <option value="approval">
              Схвальне голосування
            </option>
            <option value="copeland">
              Попарне порівняння (Коупленд)
            </option>
          </select>
          <button
            type="button"
            id="dss-voting-calculate-button"
            class="dss-voting-primary"
          >
            Розрахувати та застосувати ваги
          </button>
        </article>
      </div>

      <article class="dss-voting-card dss-voting-card-wide">
        <div class="dss-voting-card-title">
          <div>
            <h4>Голоси експертів</h4>
            <p>Ранжування критеріїв і схвалені позиції.</p>
          </div>
          <button
            type="button"
            id="dss-voting-refresh-button"
            class="dss-voting-secondary"
          >
            Оновити
          </button>
        </div>

        <div class="dss-voting-table-wrap">
          <table class="dss-voting-table">
            <thead>
              <tr>
                <th>Експерт</th>
                <th>1 місце</th>
                <th>2 місце</th>
                <th>3 місце</th>
                <th>4 місце</th>
                <th>Схвалено</th>
              </tr>
            </thead>
            <tbody id="dss-voting-ballots-body">
              <tr>
                <td colspan="6" class="dss-voting-empty">
                  Дані голосування ще не завантажені.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="dss-voting-card dss-voting-card-wide">
        <div class="dss-voting-card-title">
          <div>
            <h4>Розраховані ваги</h4>
            <p>
              Після застосування ці значення записуються
              до критеріїв моделі.
            </p>
          </div>
          <strong id="dss-voting-weight-sum">
            Сума ваг: —
          </strong>
        </div>

        <div class="dss-voting-table-wrap">
          <table class="dss-voting-table">
            <thead>
              <tr>
                <th>Місце</th>
                <th>Критерій</th>
                <th>Сирий бал</th>
                <th>Вага</th>
              </tr>
            </thead>
            <tbody id="dss-voting-results-body">
              <tr>
                <td colspan="4" class="dss-voting-empty">
                  Результат ще не розраховано.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    `;

    panel.appendChild(module);
  }

  function showMessage(message, type = "info") {
    const box = byId("dss-voting-message");

    if (!box) {
      return;
    }

    box.textContent = message;
    box.dataset.type = type;
    box.hidden = false;
  }

  function setStatus(text, type = "idle") {
    const status = byId("dss-voting-status");

    if (!status) {
      return;
    }

    status.textContent = text;
    status.dataset.type = type;
  }

  function setButtonState(button, loading, loadingText, normalText) {
    if (!button) {
      return;
    }

    button.disabled = loading;
    button.textContent = loading ? loadingText : normalText;
  }

  function groupBallots(data) {
    const matrix = data.matrix ?? {};
    const experts = data.experts ?? [];

    return experts.map((expert) => {
      const rows = [...(matrix[expert] ?? [])].sort(
        (left, right) =>
          Number(left.rank_position) - Number(right.rank_position)
      );

      return {
        expert,
        ranks: rows.map((item) => item.criterion),
        approved: rows
          .filter((item) => item.approved)
          .map((item) => item.criterion),
      };
    });
  }

  function renderBallots(data) {
    const body = byId("dss-voting-ballots-body");

    if (!body) {
      return;
    }

    const rows = groupBallots(data);

    if (rows.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="6" class="dss-voting-empty">
            Дані голосування ще не завантажені.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = rows
      .map((row) => `
        <tr>
          <td>${escapeHtml(row.expert)}</td>
          <td>${escapeHtml(row.ranks[0] ?? "—")}</td>
          <td>${escapeHtml(row.ranks[1] ?? "—")}</td>
          <td>${escapeHtml(row.ranks[2] ?? "—")}</td>
          <td>${escapeHtml(row.ranks[3] ?? "—")}</td>
          <td>${escapeHtml(row.approved.join(", ") || "—")}</td>
        </tr>
      `)
      .join("");
  }

  function renderResults(result) {
    const body = byId("dss-voting-results-body");
    const sum = byId("dss-voting-weight-sum");

    if (!body) {
      return;
    }

    const rows = result?.results ?? [];

    if (rows.length === 0) {
      body.innerHTML = `
        <tr>
          <td colspan="4" class="dss-voting-empty">
            Результат ще не розраховано.
          </td>
        </tr>
      `;

      if (sum) {
        sum.textContent = "Сума ваг: —";
      }

      return;
    }

    body.innerHTML = rows
      .map((item, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${escapeHtml(item.criterion)}</td>
          <td>${formatNumber(item.raw_score)}</td>
          <td>
            <strong>${formatNumber(item.weight)}</strong>
          </td>
        </tr>
      `)
      .join("");

    if (sum) {
      sum.textContent =
        `Сума ваг: ${formatNumber(result.weight_sum ?? 1)}`;
    }
  }

  function renderLatestStoredResults(data) {
    const method = byId("dss-voting-method")?.value;
    const stored = (data.results ?? []).filter(
      (item) => item.method === method
    );

    if (stored.length === 0) {
      renderResults(null);
      return;
    }

    const mapped = stored.map((item) => ({
      criterion: item.criterion_name,
      raw_score: item.raw_score,
      weight: item.normalized_weight,
    }));

    renderResults({
      results: mapped,
      weight_sum: mapped.reduce(
        (sum, item) => sum + Number(item.weight || 0),
        0
      ),
    });
  }

  async function loadVotingData({ silent = false } = {}) {
    try {
      const data = await requestJson(API.listVoting);

      renderBallots(data);
      renderLatestStoredResults(data);

      const expertsCount = data.experts?.length ?? 0;

      if (expertsCount > 0) {
        setStatus(`${expertsCount} експерти`, "success");

        if (!silent) {
          showMessage(
            `Завантажено голосування ${expertsCount} експертів.`,
            "success"
          );
        }
      } else {
        setStatus("Очікування даних", "idle");
      }

      return data;
    } catch (error) {
      setStatus("Помилка", "error");
      showMessage(error.message, "error");
      throw error;
    }
  }

  async function importVoting() {
    const input = byId("dss-voting-url");
    const button = byId("dss-voting-import-button");
    const url = String(input?.value ?? "").trim();

    if (!url) {
      showMessage(
        "Вставте посилання на опубліковану Google Таблицю.",
        "error"
      );
      input?.focus();
      return;
    }

    setButtonState(
      button,
      true,
      "Імпорт...",
      "Імпортувати голоси"
    );
    setStatus("Імпорт...", "loading");

    try {
      const result = await requestJson(API.importVoting, {
        method: "POST",
        body: JSON.stringify({ url }),
      });

      showMessage(
        `Імпорт завершено: ${result.imported_experts} експерти, ` +
          `${result.imported_ballots} голосів.`,
        "success"
      );

      await loadVotingData({ silent: true });
    } catch (error) {
      setStatus("Помилка", "error");
      showMessage(error.message, "error");
    } finally {
      setButtonState(
        button,
        false,
        "Імпорт...",
        "Імпортувати голоси"
      );
    }
  }

  async function calculateVoting() {
    const select = byId("dss-voting-method");
    const button = byId("dss-voting-calculate-button");
    const method = String(select?.value ?? "borda");

    setButtonState(
      button,
      true,
      "Розрахунок...",
      "Розрахувати та застосувати ваги"
    );
    setStatus("Розрахунок...", "loading");

    try {
      const result = await requestJson(API.calculateVoting, {
        method: "POST",
        body: JSON.stringify({ method }),
      });

      renderResults(result);
      setStatus(result.method_label, "success");
      showMessage(
        `${result.method_label}: ваги критеріїв розраховано ` +
          `та застосовано до моделі.`,
        "success"
      );

      if (window.RealtyVisionDSS?.refresh) {
        await window.RealtyVisionDSS.refresh();
      }
    } catch (error) {
      setStatus("Помилка", "error");
      showMessage(error.message, "error");
    } finally {
      setButtonState(
        button,
        false,
        "Розрахунок...",
        "Розрахувати та застосувати ваги"
      );
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildInterface();

    byId("dss-voting-import-button")?.addEventListener(
      "click",
      importVoting
    );

    byId("dss-voting-calculate-button")?.addEventListener(
      "click",
      calculateVoting
    );

    byId("dss-voting-refresh-button")?.addEventListener(
      "click",
      () => loadVotingData()
    );

    byId("dss-voting-method")?.addEventListener(
      "change",
      () => loadVotingData({ silent: true })
    );

    loadVotingData({ silent: true });
  });
})();
