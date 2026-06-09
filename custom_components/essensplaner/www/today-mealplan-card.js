/* Essensplaner – Lovelace card: meal plan with day navigation */

const MEAL_SLOTS = [
  { id: "breakfast", label: "Frühstück", icon: "mdi:coffee" },
  { id: "lunch", label: "Mittagessen", icon: "mdi:silverware-fork-knife" },
  { id: "dinner", label: "Abendessen", icon: "mdi:food-turkey" },
];

const WEEKDAYS = [
  "Montag",
  "Dienstag",
  "Mittwoch",
  "Donnerstag",
  "Freitag",
  "Samstag",
  "Sonntag",
];

const DEFAULT_MEAL_TIMES = {
  breakfast: { start: "07:00", end: "08:00" },
  lunch: { start: "12:00", end: "13:00" },
  dinner: { start: "18:00", end: "19:30" },
};

class TodayMealplanCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._dayOffset = 0;
    this._dayData = null;
    this._loading = false;
    this._fetchToken = 0;
    this._onClick = this._onClick.bind(this);
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && id.endsWith("_mealplan_today")
    );
    return { type: "custom:today-mealplan-card", entity: entity || "" };
  }

  static getConfigElement() {
    return document.createElement("today-mealplan-card-editor");
  }

  setConfig(config) {
    if (!config?.entity) {
      throw new Error("Entity muss gesetzt sein");
    }
    this._config = config;
  }

  connectedCallback() {
    this.addEventListener("click", this._onClick);
  }

  disconnectedCallback() {
    this.removeEventListener("click", this._onClick);
  }

  set hass(hass) {
    this._hass = hass;
    if (this._dayOffset === 0) {
      this._dayData = null;
    }
    this._render();
  }

  getCardSize() {
    return 3;
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
    return (
      state?.attributes?.config_entry_id ||
      this._config?.config_entry_id ||
      null
    );
  }

  _mealTimes(state) {
    return state?.attributes?.meal_times || DEFAULT_MEAL_TIMES;
  }

  _offsetDate(offset) {
    const base = new Date();
    base.setHours(12, 0, 0, 0);
    base.setDate(base.getDate() + offset);
    const y = base.getFullYear();
    const m = String(base.getMonth() + 1).padStart(2, "0");
    const d = String(base.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  _formatDateLabel(dateStr) {
    const parts = dateStr.split("-").map((v) => parseInt(v, 10));
    const date = new Date(parts[0], parts[1] - 1, parts[2], 12, 0, 0);
    const weekday = WEEKDAYS[(date.getDay() + 6) % 7];
    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    return `${weekday}, ${day}.${month}.${date.getFullYear()}`;
  }

  _unwrapService(res) {
    if (!res) return {};
    if (res.response !== undefined) return res.response;
    if (res.service_response !== undefined) return res.service_response;
    return res;
  }

  _parseMealplanDay(planItems, mealTimes) {
    const byType = {};
    for (const item of planItems || []) {
      if (item?.entry_type) {
        byType[item.entry_type] = item;
      }
    }

    return MEAL_SLOTS.map((slot) => {
      const item = byType[slot.id];
      const recipe = item?.recipe;
      const name = recipe?.name || item?.title || null;
      const planned = Boolean(name);
      const times = mealTimes[slot.id] || DEFAULT_MEAL_TIMES[slot.id] || {};
      return {
        entry_type: slot.id,
        label: slot.label,
        icon: slot.icon,
        name,
        image_url: recipe?.image_url || null,
        recipe_id: recipe?.id || item?.recipe_id || null,
        start_time: item?.start_time || times.start || null,
        end_time: item?.end_time || times.end || null,
        planned,
      };
    });
  }

  _currentView(state) {
    if (this._dayData?.error) {
      return {
        date: this._offsetDate(this._dayOffset),
        date_label: this._formatDateLabel(this._offsetDate(this._dayOffset)),
        meals: [],
        error: this._dayData.error,
      };
    }

    if (this._dayOffset === 0) {
      const attrs = state?.attributes || {};
      return {
        date: attrs.date || this._offsetDate(0),
        date_label: attrs.date_label || this._formatDateLabel(this._offsetDate(0)),
        meals: attrs.meals || [],
        error: null,
      };
    }

    if (this._dayData) {
      return {
        date: this._dayData.date,
        date_label: this._dayData.date_label,
        meals: this._dayData.meals,
        error: null,
      };
    }

    return {
      date: this._offsetDate(this._dayOffset),
      date_label: this._formatDateLabel(this._offsetDate(this._dayOffset)),
      meals: [],
      error: null,
    };
  }

  async _loadDay() {
    const token = ++this._fetchToken;

    if (this._dayOffset === 0) {
      this._dayData = null;
      this._loading = false;
      this._render();
      return;
    }

    const state = this._sensorState();
    const entryId = this._configEntryId(state);
    if (!entryId) {
      this._dayData = {
        error: "config_entry_id fehlt – Integration neu laden",
      };
      this._loading = false;
      this._render();
      return;
    }

    this._loading = true;
    this._render();

    const date = this._offsetDate(this._dayOffset);
    try {
      const res = await this._hass.callService(
        "essensplaner",
        "get_mealplan",
        { config_entry_id: entryId, start_date: date, end_date: date },
        undefined,
        true,
        true
      );
      if (token !== this._fetchToken) return;

      const body = this._unwrapService(res);
      const items = Array.isArray(body?.mealplan) ? body.mealplan : [];
      this._dayData = {
        date,
        date_label: this._formatDateLabel(date),
        meals: this._parseMealplanDay(items, this._mealTimes(state)),
      };
    } catch (err) {
      if (token !== this._fetchToken) return;
      this._dayData = { error: err.message || String(err) };
    }

    this._loading = false;
    this._render();
  }

  _changeDay(delta) {
    this._dayOffset += delta;
    this._loadDay();
  }

  _goToday() {
    if (this._dayOffset === 0) return;
    this._dayOffset = 0;
    this._dayData = null;
    this._loading = false;
    this._fetchToken += 1;
    this._render();
  }

  _onClick(ev) {
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const action = btn.dataset.action;
    if (action === "day-prev") this._changeDay(-1);
    if (action === "day-next") this._changeDay(1);
    if (action === "day-today") this._goToday();
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

    const view = this._currentView(state);
    const title = this._config.title || "Essensplan";
    const isToday = this._dayOffset === 0;

    const tiles = view.meals.map((meal) => {
      const planned = meal.planned && meal.name;
      const time =
        meal.start_time && meal.end_time
          ? `${meal.start_time}–${meal.end_time}`
          : "";
      const media =
        planned && meal.image_url
          ? `<img class="meal-img" src="${this._esc(meal.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<div class="meal-placeholder"><ha-icon icon="${this._esc(meal.icon || "mdi:food")}"></ha-icon></div>`;
      const body = planned
        ? `<strong class="meal-name">${this._esc(meal.name)}</strong>`
        : `<span class="meal-empty">Noch nicht geplant</span>`;
      return `
        <article class="meal-tile ${planned ? "planned" : "empty"}">
          <div class="meal-media">${media}</div>
          <div class="meal-body">
            <span class="meal-label"><ha-icon icon="${this._esc(meal.icon || "mdi:food")}"></ha-icon>${this._esc(meal.label)}</span>
            ${time ? `<span class="meal-time">${this._esc(time)}</span>` : ""}
            ${body}
          </div>
        </article>`;
    }).join("");

    const todayBtn = isToday
      ? `<span class="today-badge">Heute</span>`
      : `<button type="button" class="today-btn" data-action="day-today">Heute</button>`;

    const content = view.error
      ? `<div class="error">${this._esc(view.error)}</div>`
      : this._loading
        ? `<div class="loading"><ha-circular-progress active></ha-circular-progress></div>`
        : `<div class="grid">${tiles}</div>`;

    this.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .wrap { padding: 12px 16px 16px; }
        .head {
          display: flex; align-items: center; justify-content: space-between;
          gap: 12px; margin-bottom: 14px; flex-wrap: wrap;
        }
        .head h2 {
          margin: 0; font-size: 1.1rem; font-weight: 600;
          color: var(--primary-text-color);
        }
        .nav {
          display: inline-flex; align-items: center; gap: 4px;
        }
        .nav-btn, .today-btn {
          border: none; background: transparent; cursor: pointer;
          color: var(--primary-text-color);
          border-radius: 50%; width: 36px; height: 36px;
          display: inline-flex; align-items: center; justify-content: center;
        }
        .nav-btn:hover, .today-btn:hover {
          background: var(--secondary-background-color, rgba(0,0,0,.06));
        }
        .nav-btn ha-icon, .today-btn ha-icon { --mdc-icon-size: 22px; }
        .today-btn {
          width: auto; border-radius: 999px; padding: 0 12px;
          font-size: 0.78rem; font-weight: 600;
          color: var(--primary-color);
        }
        .date-wrap {
          display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        }
        .date { font-size: 0.85rem; color: var(--secondary-text-color); }
        .today-badge {
          font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
          letter-spacing: .04em; color: var(--primary-color);
          background: color-mix(in srgb, var(--primary-color) 14%, transparent);
          padding: 3px 8px; border-radius: 999px;
        }
        .grid {
          display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;
        }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .meal-tile {
          border-radius: 14px; overflow: hidden;
          border: 1px solid var(--divider-color, rgba(0,0,0,.12));
          background: var(--card-background-color, #fff);
          box-shadow: 0 2px 10px rgba(0,0,0,.04);
        }
        .meal-tile.empty { opacity: .88; }
        .meal-media {
          aspect-ratio: 16 / 10; background: var(--secondary-background-color, #eee);
          overflow: hidden;
        }
        .meal-img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .meal-placeholder {
          width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
          color: var(--primary-color);
          background: linear-gradient(
            135deg,
            color-mix(in srgb, var(--primary-color) 12%, var(--secondary-background-color, #f5f5f5)),
            var(--secondary-background-color, #eee)
          );
        }
        .meal-placeholder ha-icon { --mdc-icon-size: 36px; opacity: .75; }
        .meal-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 4px; }
        .meal-label {
          display: inline-flex; align-items: center; gap: 6px;
          font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
          letter-spacing: .05em; color: var(--secondary-text-color);
        }
        .meal-label ha-icon { --mdc-icon-size: 14px; }
        .meal-time { font-size: 0.75rem; color: var(--primary-color); font-weight: 500; }
        .meal-name {
          font-size: 0.92rem; line-height: 1.35; font-weight: 600;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
        }
        .meal-empty { font-size: 0.85rem; color: var(--secondary-text-color); font-style: italic; }
        .loading {
          display: flex; justify-content: center; padding: 28px 0;
        }
        .error { padding: 8px 0; color: var(--error-color, #f44336); }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="head">
            <h2>${this._esc(title)}</h2>
            <div class="date-wrap">
              <div class="nav">
                <button type="button" class="nav-btn" data-action="day-prev" title="Vorheriger Tag" aria-label="Vorheriger Tag">
                  <ha-icon icon="mdi:chevron-left"></ha-icon>
                </button>
                <span class="date">${this._esc(view.date_label)}</span>
                <button type="button" class="nav-btn" data-action="day-next" title="Nächster Tag" aria-label="Nächster Tag">
                  <ha-icon icon="mdi:chevron-right"></ha-icon>
                </button>
              </div>
              ${todayBtn}
            </div>
          </div>
          ${content}
        </div>
      </ha-card>`;
  }
}

class TodayMealplanCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this.innerHTML = `
      <div class="card-config">
        <p>Entity und Titel in der YAML-Konfiguration setzen.</p>
      </div>`;
  }
}

customElements.define("today-mealplan-card", TodayMealplanCard);
customElements.define("today-mealplan-card-editor", TodayMealplanCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "today-mealplan-card",
  name: "Essensplan",
  description: "Essensplan mit Tag-Navigation und Rezeptbildern",
  preview: true,
  documentationURL: "https://github.com/sulmaring-tech/essensplaner",
});
