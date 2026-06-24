"use strict";

const tabButtons = document.querySelectorAll(".tab-button");
const tabContents = document.querySelectorAll(".tab-content");
const notification = document.getElementById("notification");

function openTab(tabId) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabId;

    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  tabContents.forEach((content) => {
    content.classList.toggle("active", content.id === tabId);
  });

  window.history.replaceState(null, "", `#${tabId}`);
}

function showNotification(message) {
  notification.textContent = message;
  notification.classList.add("show");

  window.clearTimeout(window.dssNotificationTimeout);

  window.dssNotificationTimeout = window.setTimeout(() => {
    notification.classList.remove("show");
  }, 3500);
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    openTab(button.dataset.tab);
  });
});

document.querySelectorAll("[data-demo-message]").forEach((button) => {
  button.addEventListener("click", () => {
    showNotification(button.dataset.demoMessage);
  });
});

const requestedTab = window.location.hash.replace("#", "");

if (requestedTab && document.getElementById(requestedTab)) {
  openTab(requestedTab);
}

fetch("/api/dss/status")
  .then((response) => {
    if (!response.ok) {
      throw new Error("Не вдалося перевірити статус модуля");
    }

    return response.json();
  })
  .then((data) => {
    console.log("Статус модуля СППР:", data);
  })
  .catch((error) => {
    console.error(error);
  });
