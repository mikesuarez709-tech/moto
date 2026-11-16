"use strict";

const one = (selector, root = document) => root.querySelector(selector);
const all = (selector, root = document) => [...root.querySelectorAll(selector)];
const pesos = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });

const nav = one(".sidebar");
const navButton = one("[data-toggle-nav]");
const backdrop = one("[data-close-nav]");
function setNav(open) {
  if (!nav) return;
  nav.classList.toggle("is-open", open);
  navButton.setAttribute("aria-expanded", String(open));
  backdrop.hidden = !open;
  if (open) (one(".nav-link[aria-current]", nav) || one(".nav-link", nav))?.focus();
  else if (matchMedia("(max-width: 760px)").matches) navButton.focus();
}
navButton?.addEventListener("click", () => setNav(!nav.classList.contains("is-open")));
backdrop?.addEventListener("click", () => setNav(false));
matchMedia("(max-width: 760px)").addEventListener("change", () => {
  if (nav?.classList.contains("is-open")) setNav(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (nav?.classList.contains("is-open")) setNav(false);
  all("details.dropdown[open]").forEach((menu) => {
    menu.open = false;
    one("summary", menu)?.focus();
  });
});
document.addEventListener("click", (event) => {
  all("details.dropdown[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
all("[data-dismiss]").forEach((button) => button.addEventListener("click", () => button.closest(".flash").remove()));
all("[data-print]").forEach((button) => button.addEventListener("click", () => window.print()));

const password = one("[data-password-toggle]");
password?.addEventListener("click", () => {
  const input = document.getElementById(password.getAttribute("aria-controls"));
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  password.setAttribute("aria-label", show ? "Hide password" : "Show password");
});

const dialog = one("#confirm-dialog");
let pendingForm;
all("form[data-confirm]").forEach((form) => form.addEventListener("submit", (event) => {
  if (form.dataset.confirmed === "yes") return;
  if (form.dataset.confirmOn && form.elements.status.value !== form.dataset.confirmOn) return;
  if (!dialog?.showModal) {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    return;
  }
  event.preventDefault();
  pendingForm = form;
  one("[data-confirm-copy]", dialog).textContent = form.dataset.confirm;
  dialog.returnValue = "cancel";
  dialog.showModal();
}));
dialog?.addEventListener("close", () => {
  if (dialog.returnValue === "confirm" && pendingForm) {
    pendingForm.dataset.confirmed = "yes";
    pendingForm.requestSubmit();
    delete pendingForm.dataset.confirmed;
  }
  pendingForm = null;
});

function toggleFields(container, enabled, required = false) {
  container.hidden = !enabled;
  all("input, select", container).forEach((control) => {
    control.disabled = !enabled;
    control.required = enabled && required;
  });
}

all("[data-record-search]").forEach((input) => {
  input.addEventListener("search", () => {
    if (!input.value && input.defaultValue) input.form.requestSubmit();
  });
});

const role = one("[data-role-select]");
if (role) {
  const mechanic = one("[data-mechanic-link]");
  const update = () => toggleFields(mechanic, role.value === "mechanic", true);
  role.addEventListener("change", update);
  update();
}

const adjustment = one("[data-adjustment]");
if (adjustment) {
  const update = () => {
    const minimum = adjustment.value === "minimum";
    all("[data-stock-fields]").forEach((section) => toggleFields(section, !minimum, true));
    toggleFields(one("[data-minimum-fields]"), minimum, true);
  };
  adjustment.addEventListener("change", update);
  update();
}

const jobOwner = one("[data-job-owner]");
if (jobOwner) {
  const bike = one("[data-job-bike]");
  const update = () => {
    for (const option of Array.from(bike.options).slice(1)) {
      option.disabled = option.dataset.owner !== jobOwner.value;
      option.hidden = option.disabled;
    }
    if (bike.selectedOptions[0]?.disabled) bike.value = "";
  };
  jobOwner.addEventListener("change", update);
  update();
}

function paymentReference(form) {
  const method = one("[data-method]", form);
  const reference = one("[data-reference]", form);
  if (method && reference) reference.required = !method.disabled && method.value !== "Cash";
}
all("[data-method]").forEach((method) => {
  method.addEventListener("change", () => paymentReference(method.form));
  paymentReference(method.form);
});

const checkout = one("[data-checkout]");
if (checkout) {
  const store = one("[data-sale-rows]", checkout);
  const status = one("[data-pay-status]", checkout);
  const add = one("[data-add-line]", checkout);
  function updateTotal() {
    let totalCents = 0n;
    const cart = all("[data-sale-row]", store);
    for (const line of cart) {
      const product = one("[data-product]", line).selectedOptions[0];
      const quantity = one("[data-qty]", line);
      const qty = Number(quantity.value);
      const cents = BigInt(Math.round(Number(product?.dataset.price || 0) * 100));
      const subtotal = cents * BigInt(Number.isSafeInteger(qty) && qty > 0 ? qty : 0);
      quantity.max = String(Math.min(Number(product?.dataset.available || 100000), 100000));
      one("[data-subtotal]", line).textContent = pesos.format(Number(subtotal) / 100);
      totalCents += subtotal;
    }
    add.disabled = cart.length >= 50;
    one("[data-sale-total]", checkout).textContent = pesos.format(Number(totalCents) / 100);
    toggleFields(one("[data-pay-fields]", checkout), status.value !== "Unpaid");
    toggleFields(one("[data-partial-fields]", checkout), status.value === "Partial", true);
    paymentReference(checkout);
  }
  checkout.addEventListener("input", updateTotal);
  checkout.addEventListener("change", updateTotal);
  add.addEventListener("click", () => {
    store.append(one("#sale-line-template").content.cloneNode(true));
    updateTotal();
    one("[data-product]", store.lastElementChild).focus();
  });
  store.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-line]");
    if (!remove) return;
    remove.closest("[data-sale-row]").remove();
    if (!store.children.length) store.append(one("#sale-line-template").content.cloneNode(true));
    updateTotal();
    add.focus();
  });
  updateTotal();
}

const period = one("[data-report-period]");
if (period) {
  const start = period.form.elements.start;
  const end = period.form.elements.end;
  for (const input of [start, end]) {
    input.addEventListener("change", () => { period.value = "custom"; });
  }
  period.addEventListener("change", () => {
    if (period.value !== "custom") {
      start.value = "";
      end.value = "";
    }
  });
}

for (const chart of all("[data-chart]")) {
  const canvas = one("canvas", chart);
  const ctx = canvas.getContext("2d");
  const data = JSON.parse(chart.dataset.chart);
  const tooltip = one(".chart-tooltip", chart);
  const metric = one("[data-chart-metric]", chart.parentElement);
  const chartValue = (item) => item[metric?.value || "value"];
  if (!ctx || !data.length) continue;
  let points = [];
  let hovered = -1;
  function draw() {
    const { width, height } = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.scale(dpr, dpr);
    const left = width < 380 ? 43 : 58;
    const right = width - 13;
    const top = 18;
    const bottom = height - 29;
    const maximum = Math.max(...data.map(chartValue), 1);
    const factor = 10 ** Math.floor(Math.log10(maximum));
    const topValue = maximum <= 1 ? 4 : Math.ceil(maximum / factor) * factor;
    const label = new Intl.NumberFormat("en-PH", { notation: "compact", maximumFractionDigits: 1 });
    ctx.font = "11px DM Sans, Arial, sans-serif";
    for (let i = 0; i <= 4; i++) {
      const y = bottom - (bottom - top) * i / 4;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.strokeStyle = "#e9e8e2";
      ctx.stroke();
      ctx.fillStyle = "#676a63";
      ctx.textAlign = "right";
      ctx.fillText("₱" + label.format(topValue * i / 4), left - 7, y + 4);
    }
    const spacing = (right - left) / data.length;
    points = data.map((item, i) => {
      const x = left + spacing * (i + 0.5);
      const y = bottom - chartValue(item) / topValue * (bottom - top);
      ctx.fillStyle = "#676a63";
      ctx.textAlign = "center";
      ctx.fillText(item.label.slice(0, 3), x, bottom + 19);
      return { x, y };
    });
    const gradient = ctx.createLinearGradient(0, top, 0, bottom);
    gradient.addColorStop(0, "#ff641f40");
    gradient.addColorStop(1, "#ff641f02");
    ctx.beginPath();
    ctx.moveTo(points[0].x, bottom);
    for (const p of points) ctx.lineTo(p.x, p.y);
    ctx.lineTo(points.at(-1).x, bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.beginPath();
    points.forEach(({ x, y }, i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.strokeStyle = "#e3561a";
    ctx.lineWidth = 2.2;
    ctx.stroke();
    points.forEach(({ x, y }, i) => {
      ctx.beginPath();
      ctx.arc(x, y, hovered === i ? 4.5 : 3, 0, 2 * Math.PI);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.stroke();
    });
  }
  metric?.addEventListener("change", () => {
    canvas.setAttribute("aria-label", metric.selectedOptions[0].text + " over the last seven days");
    hovered = -1;
    tooltip.hidden = true;
    draw();
  });
  new ResizeObserver(draw).observe(canvas);
  document.fonts?.ready.then(draw);
  canvas.addEventListener("pointermove", (event) => {
    const x = event.clientX - canvas.getBoundingClientRect().left;
    if (!points.length) return;
    hovered = points.reduce((best, point, i) => Math.abs(point.x - x) < Math.abs(points[best].x - x) ? i : best, 0);
    tooltip.textContent = data[hovered].label + " · " + pesos.format(chartValue(data[hovered]));
    tooltip.hidden = false;
    tooltip.style.left = Math.max(0, Math.min(chart.clientWidth - tooltip.offsetWidth, points[hovered].x - 43)) + "px";
    draw();
  });
  canvas.addEventListener("pointerleave", () => {
    hovered = -1;
    tooltip.hidden = true;
    draw();
  });
}
