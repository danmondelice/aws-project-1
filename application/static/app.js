const toggle = document.querySelector("[data-nav-toggle]");
const nav = document.querySelector("[data-nav]");

if (toggle && nav) {
  toggle.addEventListener("click", () => nav.classList.toggle("open"));
}

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

async function sendTelemetry(payload) {
  const response = await fetch("/api/telemetry", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken},
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Telemetry request failed");
  return response.json();
}

if (csrfToken) {
  sendTelemetry({
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }).catch(() => {});
}

document.querySelector("[data-refresh-stats]")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Refreshing…";
  try {
    const response = await fetch("/api/stats");
    const stats = await response.json();
    document.querySelectorAll("[data-stat]").forEach((element) => {
      element.textContent = stats[element.dataset.stat] ?? "0";
    });
    const ranking = document.querySelector("[data-popular-routes]");
    if (ranking) {
      ranking.replaceChildren(...stats.popular_routes.map((route) => {
        const row = document.createElement("div");
        const path = document.createElement("code");
        const views = document.createElement("strong");
        path.textContent = route.path;
        views.textContent = route.views;
        row.append(path, views);
        return row;
      }));
    }
  } finally {
    button.disabled = false;
    button.textContent = "Refresh metrics";
  }
});

document.querySelector("[data-share-location]")?.addEventListener("click", (event) => {
  const status = document.querySelector("[data-location-status]");
  const button = event.currentTarget;
  if (!navigator.geolocation) {
    status.textContent = "This browser does not provide location services.";
    return;
  }
  button.disabled = true;
  status.textContent = "Waiting for your browser permission…";
  navigator.geolocation.getCurrentPosition(async (position) => {
    try {
      await sendTelemetry({
        language: navigator.language,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
      status.textContent = "Approximate location shared at two-decimal precision.";
    } catch {
      status.textContent = "The application could not store the location.";
    } finally {
      button.disabled = false;
    }
  }, () => {
    status.textContent = "Location was not shared.";
    button.disabled = false;
  }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 300000});
});
