const form = document.querySelector("#booking-form");
const date = form.elements.date;
const start = form.elements.start;
const duration = form.elements.duration;
const partySize = form.elements.party_size;
const search = document.querySelector("#search-tables");
const reserve = document.querySelector("#reserve-table");
const status = document.querySelector("#availability-status");
const tableBody = document.querySelector("#available-tables");
let pendingRequest;
let requestNumber = 0;
let optionsLoading = false;

function clearAvailability() {
  tableBody.replaceChildren();
  reserve.disabled = true;
  status.textContent = "Apply your filters to see available tables.";
}

//cancel older searches whenever filters change so their results cannot be selected
function cancelRequest() {
  requestNumber += 1;
  if (pendingRequest) pendingRequest.abort();
  search.disabled = false;
}

async function getJSON(url, parameters, signal) {
  const response = await fetch(`${url}?${parameters}`, {
    headers: { Accept: "application/json" }, signal,
  });
  if (response.redirected || response.status === 401) {
    throw new Error("Your session has ended. Log in again to continue.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Unable to load availability. Please try again.");
  return data;
}

function fillSelect(select, choices, label) {
  const previous = select.value;
  select.replaceChildren(...choices.map((value) => new Option(label(value), value)));
  if (choices.some((value) => String(value) === previous)) select.value = previous;
}

async function updateOptions() {
  cancelRequest();
  clearAvailability();
  optionsLoading = false;
  if (!date.value) return;
  const currentRequest = requestNumber;
  pendingRequest = new AbortController();
  optionsLoading = true;
  search.disabled = true;
  status.textContent = "Loading booking times...";
  try {
    const parameters = new URLSearchParams({ date: date.value });
    if (duration.value) parameters.set("duration", duration.value);
    const data = await getJSON(form.dataset.optionsUrl, parameters, pendingRequest.signal);
    if (currentRequest !== requestNumber) return;
    fillSelect(duration, data.durations, (value) => `${value} minutes`);
    fillSelect(start, data.starts, (value) => value);
    status.textContent = data.starts.length ? "Apply your filters to see available tables." : "No start times are available for this date and duration.";
  } catch (error) {
    if (currentRequest === requestNumber && error.name !== "AbortError") {
      start.replaceChildren();
      status.textContent = error instanceof SyntaxError ? "Unable to load booking times. Please try again." : error.message;
    }
  } finally {
    if (currentRequest === requestNumber) {
      optionsLoading = false;
      search.disabled = !start.value;
    }
  }
}

function showTables(tables) {
  for (const table of tables) {
    const row = document.createElement("tr");
    const selection = document.createElement("td");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "table_id";
    radio.value = table.id;
    radio.setAttribute("aria-label", `Select table ${table.label}`);
    selection.append(radio);
    const label = document.createElement("td");
    label.textContent = table.label;
    const capacity = document.createElement("td");
    capacity.textContent = `${table.capacity} guests`;
    row.append(selection, label, capacity);
    tableBody.append(row);
  }
}

search.addEventListener("click", async () => {
  cancelRequest();
  clearAvailability();
  // Validate search fields without requiring a table selection before the search
  if (![date, start, duration, partySize].every((field) => field.reportValidity())) return;
  const currentRequest = requestNumber;
  pendingRequest = new AbortController();
  search.disabled = true;
  status.textContent = "Searching for available tables...";
  try {
    const parameters = new URLSearchParams({ date: date.value, start: start.value, duration: duration.value, party_size: partySize.value });
    const data = await getJSON(form.dataset.availabilityUrl, parameters, pendingRequest.signal);
    if (currentRequest !== requestNumber) return;
    showTables(data.tables);
    status.textContent = data.tables.length ? "Select an available table below." : "No tables are available for this visit. Try a different time or party size.";
  } catch (error) {
    if (currentRequest === requestNumber && error.name !== "AbortError") {
      status.textContent = error instanceof SyntaxError ? "Unable to load availability. Please try again." : error.message;
    }
  } finally {
    if (currentRequest === requestNumber) search.disabled = false;
  }
});

date.addEventListener("change", updateOptions);
duration.addEventListener("change", updateOptions);
for (const field of [start, partySize]) {
  field.addEventListener("input", () => {
    if (!optionsLoading) cancelRequest();
    clearAvailability();
  });
}
tableBody.addEventListener("change", () => {
  reserve.disabled = !tableBody.querySelector('input[name="table_id"]:checked');
});
form.addEventListener("submit", (event) => {
  if (reserve.disabled || !tableBody.querySelector('input[name="table_id"]:checked')) {
    event.preventDefault();
    status.textContent = "Search availability and select a table first.";
  } else {
    reserve.disabled = true;
  }
});
