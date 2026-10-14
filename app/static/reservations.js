const filters = document.querySelector("#reservation-filters");
const rows = document.querySelector("#reservation-rows");
const feedback = document.querySelector("#history-feedback");
let controller;
let sequence = 0;
let canceling = false;

async function readResponse(response) {
  if (response.redirected || response.status === 401) {
    throw new Error("Your session has ended. Sign in again to continue.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Unable to update reservations. Please try again.");
  return data;
}

async function refresh(successMessage = "") {
  controller?.abort();
  controller = new AbortController();
  const current = ++sequence;
  feedback.textContent = successMessage || "Loading reservations...";
  rows.setAttribute("aria-busy", "true");
  try {
    const parameters = new URLSearchParams(new FormData(filters));
    const response = await fetch(`${filters.dataset.filterUrl}?${parameters}`, {
      headers: { Accept: "application/json" }, signal: controller.signal,
    });
    const data = await readResponse(response);
    if (current !== sequence) return;
    // Rows are escaped by the server's Jinja template, not assembled from user input
    rows.innerHTML = data.html;
    feedback.textContent = successMessage || `${data.count} reservation(s) found.`;
  } catch (error) {
    if (current === sequence && error.name !== "AbortError") {
      feedback.textContent = successMessage
        ? `${successMessage} Refresh failed. Apply the filters again.`
        : (error instanceof SyntaxError ? "Unable to load reservations. Please try again." : error.message);
    }
  } finally {
    if (current === sequence) rows.removeAttribute("aria-busy");
  }
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  refresh();
});
filters.addEventListener("input", () => {
  controller?.abort();
  ++sequence;
  rows.removeAttribute("aria-busy");
  feedback.textContent = "Apply your filters to update the list.";
});

rows.addEventListener("submit", async (event) => {
  const form = event.target.closest(".cancel-reservation");
  if (!form) return;
  event.preventDefault();
  if (canceling) return;
  canceling = true;
  controller?.abort();
  ++sequence;
  rows.removeAttribute("aria-busy");
  rows.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  feedback.textContent = "Canceling reservation...";
  try {
    const response = await fetch(form.action, {
      method: "POST", headers: { Accept: "application/json" }, body: new FormData(form),
    });
    const data = await readResponse(response);
    await refresh(data.message);
  } catch (error) {
    feedback.textContent = error instanceof SyntaxError ? "Unable to cancel. Refresh the list and try again." : error.message;
  } finally {
    canceling = false;
    rows.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }
});
