(() => {
  "use strict";

  const METHOD_MAP = {
    additive: "additive",
    "адитивний": "additive",
    cautious: "cautious",
    "обережний": "cautious",
    "мінімум": "cautious",
    multiplicative: "multiplicative",
    "мультиплікативний": "multiplicative",
  };

  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatScore(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(3) : "0.000";
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

    const payload = await response.json();

    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || `HTTP ${response.status}`);
    }

    return payload.data ?? payload;
  }

  function showMessage(message, type = "info") {
    const box = $("dss-results-message");

    if (!box) {
      console[type === "error" ? "error" : "log"](message);
      return;
    }

    box.textContent = message;
    box.hidden = false;
    box.dataset.type = type;
  }

  function selectedMethod() {
    const select = $("dss-method-select");

    if (!select) {
      return "additive";
    }

    const raw = String(select.value || select.options[select.selectedIndex]?.text || "")
      .trim()
      .toLowerCase();

    return METHOD_MAP[raw] || "additive";
  }

  function renderRanking(data) {
    const body = $("dss-ranking-body");

    if (!body) {
      return;
    }

    const ranking = Array.isArray(data.ranking) ? data.ranking : [];

    body.innerHTML = ranking
      .map((item) => {
        const statusLabel =
          item.status === "recommended"
            ? "Рекомендовано"
            : item.status === "excluded"
              ? "Виключено"
              : "Допустима";

        return `
          <tr class="${item.status === "recommended" ? "recommended-row" : ""}">
            <td>${item.place ?? "—"}</td>
            <td>${escapeHtml(item.alternative)}</td>
            <td>${formatScore(item.score)}</td>
            <td>${statusLabel}</td>
          </tr>
        `;
      })
      .join("");
  }

  function renderBestAlternative(data) {
    const best = data.best_alternative;

    const name = $("dss-best-name");
    const score = $("dss-best-score");
    const reasons = $("dss-best-reasons");

    if (!best) {
      if (name) name.textContent = "Допустимих альтернатив немає";
      if (score) score.textContent = "—";
      if (reasons) {
        reasons.innerHTML =
          "<li>Усі альтернативи відхилено пороговими обмеженнями.</li>";
      }
      return;
    }

    if (name) {
      name.textContent = best.alternative;
    }

    if (score) {
      score.textContent = formatScore(best.score);
    }

    if (reasons) {
      const explanation = Array.isArray(best.explanation)
        ? best.explanation
        : [];

      reasons.innerHTML = explanation
        .map((reason) => `<li>${escapeHtml(reason)}</li>`)
        .join("");
    }
  }

  async function calculateRanking() {
    const button = $("dss-calculate-button");

    if (button) {
      button.disabled = true;
      button.textContent = "Обчислення...";
    }

    try {
      const data = await requestJson("/api/dss/calculate", {
        method: "POST",
        body: JSON.stringify({
          method: selectedMethod(),
        }),
      });

      renderRanking(data);
      renderBestAlternative(data);
      showMessage("Рейтинг успішно розраховано.", "success");
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Розрахувати рейтинг";
      }
    }
  }

  async function loadCriteriaForSensitivity() {
    const select = $("dss-sensitivity-criterion");

    if (!select) {
      return;
    }

    try {
      const criteria = await requestJson(
        "/api/dss/criteria?include_inactive=false"
      );

      select.innerHTML = criteria
        .map(
          (criterion) => `
            <option value="${criterion.id}" data-weight="${criterion.weight}">
              ${escapeHtml(criterion.name)}
            </option>
          `
        )
        .join("");

      syncSensitivityWeight();
    } catch (error) {
      showMessage(error.message, "error");
    }
  }

  function syncSensitivityWeight() {
    const criterionSelect = $("dss-sensitivity-criterion");
    const weightInput = $("dss-sensitivity-weight");

    if (!criterionSelect || !weightInput) {
      return;
    }

    const option = criterionSelect.options[criterionSelect.selectedIndex];

    if (option?.dataset.weight) {
      weightInput.value = option.dataset.weight;
    }
  }

  async function runSensitivityAnalysis() {
    const criterionSelect = $("dss-sensitivity-criterion");
    const weightInput = $("dss-sensitivity-weight");
    const output = $("dss-sensitivity-result");
    const button = $("dss-sensitivity-button");

    if (!criterionSelect || !weightInput) {
      return;
    }

    const criterionId = Number(criterionSelect.value);
    const newWeight = Number(weightInput.value);

    if (!Number.isFinite(newWeight) || newWeight < 0 || newWeight > 1) {
      showMessage("Нова вага повинна бути в межах від 0 до 1.", "error");
      return;
    }

    if (button) {
      button.disabled = true;
    }

    try {
      const data = await requestJson("/api/dss/sensitivity", {
        method: "POST",
        body: JSON.stringify({
          criterion_id: criterionId,
          new_weight: newWeight,
          method: selectedMethod(),
        }),
      });

      if (output) {
        output.innerHTML = `
          <strong>${escapeHtml(data.explanation)}</strong>
          <div>
            Критерій: ${escapeHtml(data.criterion)}.
            Стара вага: ${Number(data.old_weight).toFixed(3)}.
            Нова вага: ${Number(data.new_weight).toFixed(3)}.
          </div>
        `;
      }

      renderRanking(data.changed);
      renderBestAlternative(data.changed);
      showMessage("Аналіз чутливості виконано.", "success");
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  function activateHashTab() {
    const hash = window.location.hash.replace("#", "");

    if (!hash) {
      return;
    }

    const directTarget =
      document.querySelector(`[data-tab="${hash}"]`) ||
      document.querySelector(`[href="#${hash}"]`);

    if (directTarget) {
      directTarget.click();
      return;
    }

    if (hash === "results") {
      const candidates = [...document.querySelectorAll("button, a")];
      const resultsTab = candidates.find((element) =>
        element.textContent?.includes("Результати та аналіз")
      );

      resultsTab?.click();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    activateHashTab();

    $("dss-calculate-button")?.addEventListener(
      "click",
      calculateRanking
    );

    $("dss-sensitivity-button")?.addEventListener(
      "click",
      runSensitivityAnalysis
    );

    $("dss-sensitivity-criterion")?.addEventListener(
      "change",
      syncSensitivityWeight
    );

    loadCriteriaForSensitivity();

    if (window.location.hash === "#results") {
      calculateRanking();
    }
  });
})();
