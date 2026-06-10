/* Essensplaner – Lovelace card: weekly meal plan grid */

const MEAL_ORDER = [
  "breakfast",
  "lunch",
  "side_lunch",
  "dinner",
  "side_dinner",
  "dessert",
  "drink",
  "snack",
];

const DAY_LABELS = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"];

const DEFAULT_COLORS = {
  breakfast: "#e67e22",
  lunch: "#2d6a4f",
  side_lunch: "#48cae4",
  dinner: "#7b2cbf",
  side_dinner: "#e07a5f",
  dessert: "#c1121f",
  drink: "#0077b6",
  snack: "#f4a261",
};

const COLOR_LABELS = {
  breakfast: "Frühstück",
  lunch: "Mittagessen",
  side_lunch: "Beilage (Mittag)",
  dinner: "Abendessen",
  side_dinner: "Beilage (Abend)",
  dessert: "Dessert",
  drink: "Getränk",
  snack: "Snack",
};

class WeekMealplanCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._weekOffset = 0;
    this._weekData = null;
    this._loading = false;
    this._fetchToken = 0;
    this._lastChanged = null;
    this._lastFetch = 0;
    this._onClick = this._onClick.bind(this);
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && id.endsWith("_mealplan_today")
    );
    return {
      type: "custom:week-mealplan-card",
      entity: entity || "",
      title: "Essensplan",
      colors: { ...DEFAULT_COLORS },
    };
  }

  static getConfigElement() {
    return document.createElement("week-mealplan-card-editor");
  }

  setConfig(config) {
    if (!config?.entity) {
      throw new Error("Entity muss gesetzt sein");
    }
    this._config = {
      colors: { ...DEFAULT_COLORS, ...(config.colors || {}) },
      week_start: config.week_start || "monday",
      ...config,
    };
  }

  connectedCallback() {
    this.addEventListener("click", this._onClick);
  }

  disconnectedCallback() {
    this.removeEventListener("click", this._onClick);
  }

  set hass(hass) {
    this._hass = hass;
    const state = this._sensorState();
    const sensorChanged = state?.last_changed !== this._lastChanged;
    this._lastChanged = state?.last_changed;
    const now = Date.now();
    const stale = !this._lastFetch || now - this._lastFetch > 60000;
    if (!this._weekData || sensorChanged || stale) {
      this._loadWeek();
    } else {
      this._render();
    }
  }

  getCardSize() {
    return 4;
  }

  _colors() {
    return { ...DEFAULT_COLORS, ...(this._config?.colors || {}) };
  }

  _esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  _sensorState() {
    return this._hass?.states[this._config?.entity];
  }

  _configEntryId(state) {
    return state?.attributes?.config_entry_id || this._config?.config_entry_id || null;
  }

  _todayIso() {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  _weekRange() {
    const anchor = new Date();
    anchor.setHours(12, 0, 0, 0);
    anchor.setDate(anchor.getDate() + this._weekOffset * 7);
    const weekStart = new Date(anchor);
    const dow = weekStart.getDay();
    if (this._config?.week_start === "sunday") {
      weekStart.setDate(weekStart.getDate() - dow);
    } else {
      const diff = dow === 0 ? -6 : 1 - dow;
      weekStart.setDate(weekStart.getDate() + diff);
    }
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate() + i);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return {
        iso: `${y}-${m}-${day}`,
        dayNum: d.getDate(),
        label: DAY_LABELS[i],
        isToday: `${y}-${m}-${day}` === this._todayIso(),
      };
    });
    const weekEnd = days[6].iso;
    return { start: days[0].iso, end: weekEnd, days };
  }

  _unwrapService(res) {
    if (!res) return {};
    if (res.response !== undefined) return res.response;
    if (res.service_response !== undefined) return res.service_response;
    return res;
  }

  _entryName(item) {
    return item?.recipe?.name || item?.title || null;
  }

  _groupByDay(items) {
    const grouped = {};
    for (const item of items || []) {
      if (!item?.date) continue;
      const name = this._entryName(item);
      if (!name) continue;
      if (!grouped[item.date]) grouped[item.date] = [];
      grouped[item.date].push({
        entry_type: item.entry_type,
        name,
        sort: MEAL_ORDER.indexOf(item.entry_type),
      });
    }
    for (const date of Object.keys(grouped)) {
      grouped[date].sort((a, b) => {
        const sa = a.sort === -1 ? 99 : a.sort;
        const sb = b.sort === -1 ? 99 : b.sort;
        return sa - sb;
      });
    }
    return grouped;
  }

  async _loadWeek() {
    if (!this._hass || !this._config) return;
    const token = ++this._fetchToken;
    const state = this._sensorState();
    const entryId = this._configEntryId(state);

    if (!entryId) {
      this._weekData = { error: "config_entry_id fehlt – Entity prüfen oder Integration neu laden" };
      this._loading = false;
      this._render();
      return;
    }

    this._loading = true;
    this._render();

    const range = this._weekRange();
    try {
      const res = await this._hass.callService(
        "essensplaner",
        "get_mealplan",
        {
          config_entry_id: entryId,
          start_date: range.start,
          end_date: range.end,
        },
        undefined,
        true,
        true
      );
      if (token !== this._fetchToken) return;
      const body = this._unwrapService(res);
      const items = Array.isArray(body?.mealplan) ? body.mealplan : [];
      this._weekData = { grouped: this._groupByDay(items), range };
      this._lastFetch = Date.now();
    } catch (err) {
      if (token !== this._fetchToken) return;
      this._weekData = { error: err.message || String(err) };
    }

    this._loading = false;
    this._render();
  }

  _changeWeek(delta) {
    this._weekOffset += delta;
    this._loadWeek();
  }

  _goCurrentWeek() {
    if (this._weekOffset === 0) return;
    this._weekOffset = 0;
    this._loadWeek();
  }

  _onClick(ev) {
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const action = btn.dataset.action;
    if (action === "week-prev") this._changeWeek(-1);
    if (action === "week-next") this._changeWeek(1);
    if (action === "week-today") this._goCurrentWeek();
  }

  _renderDayColumn(day, entries) {
    const colors = this._colors();
    const blocks = entries.length
      ? entries
          .map((entry) => {
            const bg = colors[entry.entry_type] || colors.dinner || "#5e35b1";
            return `
              <div class="event-block" style="--event-bg:${this._esc(bg)}">
                <span class="event-name">${this._esc(entry.name)}</span>
              </div>`;
          })
          .join("")
      : `<div class="no-events">Keine Ereignisse</div>`;

    return `
      <div class="day-col ${day.isToday ? "today" : ""}">
        <div class="day-head">
          <span class="day-wd">${day.label}</span>
          <span class="day-num">${day.dayNum}</span>
        </div>
        <div class="day-events">${blocks}</div>
      </div>`;
  }

  _weekLabel(range) {
    if (!range?.days?.length) return "";
    const first = range.days[0];
    const last = range.days[6];
    const fmt = (iso) => {
      const [, m, d] = iso.split("-");
      return `${d}.${m}.`;
    };
    return `${fmt(first.iso)} – ${fmt(last.iso)}${last.iso.slice(0, 4)}`;
  }

  _render() {
    if (!this._config || !this._hass) return;

    const state = this._sensorState();
    if (!state) {
      this.innerHTML = `
        <ha-card header="Essensplan">
          <div class="card-content error">Entity nicht gefunden: ${this._esc(this._config.entity)}</div>
        </ha-card>`;
      return;
    }

    const title = this._config.title || "Essensplan";
    const range = this._weekData?.range || this._weekRange();
    const grouped = this._weekData?.grouped || {};
    const onCurrentWeek = this._weekOffset === 0;

    const columns = range.days
      .map((day) => this._renderDayColumn(day, grouped[day.iso] || []))
      .join("");

    const content = this._weekData?.error
      ? `<div class="error">${this._esc(this._weekData.error)}</div>`
      : this._loading
        ? `<div class="loading"><ha-circular-progress active></ha-circular-progress></div>`
        : `<div class="week-grid">${columns}</div>`;

    this.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .wrap { padding: 14px 16px 18px; }
        .head {
          display: flex; align-items: center; justify-content: space-between;
          gap: 12px; margin-bottom: 16px; flex-wrap: wrap;
        }
        .head h2 {
          margin: 0; font-size: 1.15rem; font-weight: 700;
          color: var(--primary-text-color);
        }
        .nav {
          display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap;
        }
        .nav-btn, .today-btn {
          border: none; background: transparent; cursor: pointer;
          color: var(--primary-text-color);
          border-radius: 50%; width: 34px; height: 34px;
          display: inline-flex; align-items: center; justify-content: center;
        }
        .nav-btn:hover, .today-btn:hover {
          background: var(--secondary-background-color, rgba(255,255,255,.08));
        }
        .nav-btn ha-icon { --mdc-icon-size: 22px; }
        .week-label {
          font-size: 0.82rem; color: var(--secondary-text-color); min-width: 88px; text-align: center;
        }
        .today-btn {
          width: auto; border-radius: 999px; padding: 0 12px; height: 30px;
          font-size: 0.76rem; font-weight: 600; color: var(--primary-color);
        }
        .week-grid {
          display: grid; grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 0; min-height: 180px;
          border-top: 1px solid var(--divider-color, rgba(255,255,255,.12));
        }
        @media (max-width: 900px) {
          .week-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px; border-top: none;
          }
          .day-col { border-right: none !important; border: 1px solid var(--divider-color, rgba(255,255,255,.1)); border-radius: 12px; }
        }
        @media (max-width: 520px) {
          .week-grid { grid-template-columns: 1fr; }
        }
        .day-col {
          display: flex; flex-direction: column; min-width: 0;
          border-right: 1px solid var(--divider-color, rgba(255,255,255,.1));
        }
        .day-col:last-child { border-right: none; }
        .day-head {
          display: flex; flex-direction: column; align-items: center; gap: 2px;
          padding: 10px 6px 8px; border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.1));
        }
        .day-wd {
          font-size: 0.72rem; font-weight: 700; letter-spacing: .06em;
          color: var(--secondary-text-color); text-transform: uppercase;
        }
        .day-num {
          font-size: 1.35rem; font-weight: 700; line-height: 1.1;
          color: var(--primary-text-color);
        }
        .day-col.today .day-num { color: var(--primary-color); }
        .day-events {
          display: flex; flex-direction: column; gap: 6px;
          padding: 8px 6px 10px; flex: 1;
        }
        .event-block {
          background: var(--event-bg, #5e35b1);
          border-radius: 6px; padding: 8px 8px;
          min-height: 36px; display: flex; align-items: center;
          box-shadow: 0 1px 2px rgba(0,0,0,.18);
        }
        .event-name {
          color: #fff; font-size: 0.72rem; font-weight: 600; line-height: 1.35;
          display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
          word-break: break-word;
        }
        .no-events {
          flex: 1; display: flex; align-items: flex-start; justify-content: center;
          padding: 12px 4px; text-align: center;
          font-size: 0.72rem; color: var(--secondary-text-color);
        }
        .loading { display: flex; justify-content: center; padding: 40px 0; }
        .error { padding: 8px 0; color: var(--error-color, #f44336); }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="head">
            <h2>${this._esc(title)}</h2>
            <div class="nav">
              <button type="button" class="nav-btn" data-action="week-prev" title="Vorherige Woche" aria-label="Vorherige Woche">
                <ha-icon icon="mdi:chevron-left"></ha-icon>
              </button>
              <span class="week-label">${this._esc(this._weekLabel(range))}</span>
              <button type="button" class="nav-btn" data-action="week-next" title="Nächste Woche" aria-label="Nächste Woche">
                <ha-icon icon="mdi:chevron-right"></ha-icon>
              </button>
              ${onCurrentWeek
                ? ""
                : `<button type="button" class="today-btn" data-action="week-today">Diese Woche</button>`}
            </div>
          </div>
          ${content}
        </div>
      </ha-card>`;
  }
}

class WeekMealplanCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      colors: { ...DEFAULT_COLORS, ...(config?.colors || {}) },
      week_start: config?.week_start || "monday",
      entity: config?.entity || "",
      title: config?.title || "Essensplan",
      ...config,
    };
    this._render();
  }

  _fireConfig(changed) {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        bubbles: true,
        composed: true,
        detail: { config: changed },
      })
    );
  }

  _render() {
    const colors = { ...DEFAULT_COLORS, ...(this._config.colors || {}) };
    const colorFields = MEAL_ORDER.map(
      (id) => `
        <div class="color-row">
          <label>${COLOR_LABELS[id] || id}</label>
          <input type="color" data-color="${id}" value="${colors[id]}">
          <input type="text" class="color-text" data-color-text="${id}" value="${colors[id]}">
        </div>`
    ).join("");

    this.innerHTML = `
      <style>
        .editor { padding: 8px 0; display: flex; flex-direction: column; gap: 12px; }
        .hint { margin: 0; font-size: 0.85rem; color: var(--secondary-text-color); }
        .color-grid { display: grid; gap: 8px; }
        .color-row {
          display: grid; grid-template-columns: 1fr 40px 92px; gap: 8px; align-items: center;
        }
        .color-row label { font-size: 0.85rem; }
        .color-row input[type="color"] {
          width: 40px; height: 32px; padding: 0; border: none; background: transparent; cursor: pointer;
        }
        .color-text {
          font: inherit; font-size: 0.82rem; padding: 6px 8px; border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff); color: var(--primary-text-color);
        }
        select, input[type="text"].field {
          font: inherit; padding: 8px 10px; border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff); color: var(--primary-text-color);
        }
      </style>
      <div class="editor">
        <p class="hint">Entity und Titel in der YAML-Konfiguration. Farben hier anpassen:</p>
        <label>Titel
          <input class="field" type="text" id="title" value="${this._config.title || "Essensplan"}">
        </label>
        <label>Wochenstart
          <select id="week_start">
            <option value="monday" ${this._config.week_start !== "sunday" ? "selected" : ""}>Montag</option>
            <option value="sunday" ${this._config.week_start === "sunday" ? "selected" : ""}>Sonntag</option>
          </select>
        </label>
        <div class="color-grid">${colorFields}</div>
      </div>`;

    this.querySelector("#title")?.addEventListener("change", (ev) => {
      this._fireConfig({ ...this._config, title: ev.target.value });
    });
    this.querySelector("#week_start")?.addEventListener("change", (ev) => {
      this._fireConfig({ ...this._config, week_start: ev.target.value });
    });

    for (const id of MEAL_ORDER) {
      const picker = this.querySelector(`[data-color="${id}"]`);
      const text = this.querySelector(`[data-color-text="${id}"]`);
      const update = (value) => {
        const colors = { ...DEFAULT_COLORS, ...(this._config.colors || {}), [id]: value };
        this._fireConfig({ ...this._config, colors });
        if (picker && picker.value !== value) picker.value = value;
        if (text && text.value !== value) text.value = value;
      };
      picker?.addEventListener("input", (ev) => update(ev.target.value));
      text?.addEventListener("change", (ev) => {
        const val = ev.target.value.trim();
        if (/^#[0-9a-fA-F]{6}$/.test(val)) update(val);
      });
    }
  }
}

customElements.define("week-mealplan-card", WeekMealplanCard);
customElements.define("week-mealplan-card-editor", WeekMealplanCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "week-mealplan-card",
  name: "Essensplan Woche",
  description: "Wochenübersicht des Essensplans mit konfigurierbaren Farben",
  preview: false,
  documentationURL: "https://github.com/sulmaring-tech/essensplaner",
});
