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

const ALL_MEAL_LABELS = {
  breakfast: "Frühstück",
  lunch: "Mittagessen",
  side_lunch: "Beilage (Mittag)",
  dinner: "Abendessen",
  side_dinner: "Beilage (Abend)",
  dessert: "Dessert",
  drink: "Getränk",
  snack: "Snack",
};

function formatIngredient(item) {
  if (!item) return "";
  if (typeof item === "string") return item;
  const parts = [];
  if (item.quantity != null && item.quantity !== "") {
    parts.push(String(item.quantity).replace(".", ","));
  }
  if (item.unit) parts.push(item.unit);
  if (item.name) parts.push(item.name);
  let text = parts.join(" ").trim();
  if (item.note) text += ` (${item.note})`;
  return text || "";
}

function formatServings(servings) {
  if (!servings) return null;
  const text = String(servings).trim();
  const match = text.match(/(\d+)/);
  if (!match) return text;
  const count = parseInt(match[1], 10);
  if (Number.isNaN(count)) return text;
  return count === 1 ? "1 Portion" : `${count} Portionen`;
}

function formatDuration(minutes) {
  if (!minutes) return null;
  const mins = Number(minutes);
  if (Number.isNaN(mins) || mins <= 0) return null;
  if (mins < 60) return `${mins} Min.`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h} Std. ${m} Min.` : `${h} Std.`;
}

class TodayMealplanCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._dayOffset = 0;
    this._dayData = null;
    this._loading = false;
    this._fetchToken = 0;
    this._detail = null;
    this._detailToken = 0;
    this._onClick = this._onClick.bind(this);
    this._onKeydown = this._onKeydown.bind(this);
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
    this.addEventListener("keydown", this._onKeydown);
  }

  disconnectedCallback() {
    this.removeEventListener("click", this._onClick);
    this.removeEventListener("keydown", this._onKeydown);
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
    this._closeDetail();
    this._dayOffset += delta;
    this._loadDay();
  }

  _goToday() {
    if (this._dayOffset === 0) return;
    this._closeDetail();
    this._dayOffset = 0;
    this._dayData = null;
    this._loading = false;
    this._fetchToken += 1;
    this._render();
  }

  _onKeydown(ev) {
    if (ev.key === "Escape" && this._detail) {
      ev.preventDefault();
      this._closeDetail();
    }
  }

  _onClick(ev) {
    if (ev.target.classList.contains("detail-overlay")) {
      this._closeDetail();
      return;
    }
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const action = btn.dataset.action;
    if (action === "day-prev") this._changeDay(-1);
    if (action === "day-next") this._changeDay(1);
    if (action === "day-today") this._goToday();
    if (action === "show-detail") this._openDetail(btn.dataset.type);
    if (action === "detail-close") this._closeDetail();
  }

  _closeDetail() {
    if (!this._detail) return;
    this._detail = null;
    this._detailToken += 1;
    this._render();
  }

  async _openDetail(entryType) {
    const state = this._sensorState();
    const entryId = this._configEntryId(state);
    const view = this._currentView(state);
    const date = view.date;
    if (!entryId || !entryType) return;

    const token = ++this._detailToken;
    this._detail = { loading: true, entryType, date };
    this._render();

    try {
      const res = await this._hass.callService(
        "essensplaner",
        "get_mealplan",
        { config_entry_id: entryId, start_date: date, end_date: date },
        undefined,
        true,
        true
      );
      if (token !== this._detailToken) return;
      const body = this._unwrapService(res);
      const items = Array.isArray(body?.mealplan) ? body.mealplan : [];
      const item = items.find((i) => i.entry_type === entryType);
      if (!item) {
        this._detail = { error: "Eintrag nicht gefunden", entryType, date };
      } else {
        this._detail = { item, entryType, date, loading: false };
      }
    } catch (err) {
      if (token !== this._detailToken) return;
      this._detail = { error: err.message || String(err), entryType, date, loading: false };
    }
    this._render();
  }

  _detailTitle(item) {
    return item?.recipe?.name || item?.title || "Essensdetails";
  }

  _renderRecipeThumb(recipe) {
    const url = recipe?.image_url;
    if (url) {
      return `<img class="detail-img" src="${this._esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
    }
    return `<div class="detail-img placeholder"><ha-icon icon="mdi:food"></ha-icon></div>`;
  }

  _renderMetaChips(recipe) {
    if (!recipe) return "";
    const chips = [];
    const portions = formatServings(recipe.servings);
    if (portions) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:account-group"></ha-icon>${this._esc(portions)}</span>`);
    }
    const prep = formatDuration(recipe.prep_time);
    if (prep) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:knife"></ha-icon>${prep}</span>`);
    }
    const cook = formatDuration(recipe.cook_time);
    if (cook) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:stove"></ha-icon>${cook}</span>`);
    }
    if (!chips.length) return "";
    return `<div class="meta-chips">${chips.join("")}</div>`;
  }

  _renderDetailBody(item, dateLabel) {
    const recipe = item?.recipe;
    const mealLabel = ALL_MEAL_LABELS[item.entry_type] || item.entry_type;
    const mealIcon =
      MEAL_SLOTS.find((s) => s.id === item.entry_type)?.icon || "mdi:food";
    const time =
      item.start_time && item.end_time
        ? `${item.start_time}–${item.end_time}`
        : "";

    if (recipe) {
      const ings = (recipe.ingredients || [])
        .map((i) => `<li>${this._esc(formatIngredient(i))}</li>`)
        .join("");
      const steps = (recipe.instructions || [])
        .map(
          (s, idx) =>
            `<li><span class="step-num">${idx + 1}</span><span class="step-text">${this._esc(s)}</span></li>`
        )
        .join("");
      const source = recipe.source_url
        ? `<a class="source-link" href="${this._esc(recipe.source_url)}" target="_blank" rel="noopener">Originalrezept öffnen</a>`
        : "";
      return `
        <div class="detail-hero">${this._renderRecipeThumb(recipe)}</div>
        <div class="detail-content">
          <p class="detail-meta">
            <span class="meal-badge"><ha-icon icon="${mealIcon}"></ha-icon>${this._esc(mealLabel)}</span>
            <span>${this._esc(dateLabel)}</span>
            ${time ? `<span>${this._esc(time)}</span>` : ""}
          </p>
          <h3 class="detail-title">${this._esc(recipe.name)}</h3>
          ${this._renderMetaChips(recipe)}
          ${recipe.description ? `<p class="detail-desc">${this._esc(recipe.description)}</p>` : ""}
          ${source}
          <div class="detail-sections">
            <section class="detail-panel">
              <h4><ha-icon icon="mdi:basket"></ha-icon> Zutaten</h4>
              <ul class="ingredient-list">${ings || "<li class='muted'>Keine Zutaten</li>"}</ul>
            </section>
            <section class="detail-panel">
              <h4><ha-icon icon="mdi:pot-steam"></ha-icon> Zubereitung</h4>
              <ol class="step-list">${steps || "<li class='muted'>Keine Schritte</li>"}</ol>
            </section>
          </div>
        </div>`;
    }

    const title = item.title || "Notiz";
    const desc = item.description || "";
    return `
      <div class="detail-content note-detail">
        <p class="detail-meta">
          <span class="meal-badge"><ha-icon icon="${mealIcon}"></ha-icon>${this._esc(mealLabel)}</span>
          <span>${this._esc(dateLabel)}</span>
          ${time ? `<span>${this._esc(time)}</span>` : ""}
        </p>
        <h3 class="detail-title">${this._esc(title)}</h3>
        ${desc ? `<p class="detail-desc">${this._esc(desc)}</p>` : `<p class="muted">Keine weitere Beschreibung.</p>`}
      </div>`;
  }

  _renderDetailOverlay(dateLabel) {
    if (!this._detail) return "";
    if (this._detail.loading) {
      return `
        <div class="detail-overlay" role="presentation">
          <div class="detail-dialog" role="dialog" aria-modal="true" aria-label="Essensdetails">
            <div class="detail-head">
              <h3>Essensdetails</h3>
              <button type="button" class="detail-close" data-action="detail-close" title="Schließen" aria-label="Schließen">
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>
            <div class="detail-scroll detail-loading">
              <ha-circular-progress active></ha-circular-progress>
            </div>
          </div>
        </div>`;
    }
    if (this._detail.error) {
      return `
        <div class="detail-overlay" role="presentation">
          <div class="detail-dialog" role="dialog" aria-modal="true">
            <div class="detail-head">
              <h3>Fehler</h3>
              <button type="button" class="detail-close" data-action="detail-close" title="Schließen" aria-label="Schließen">
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>
            <div class="detail-scroll"><p class="error">${this._esc(this._detail.error)}</p></div>
          </div>
        </div>`;
    }
    const item = this._detail.item;
    return `
      <div class="detail-overlay" role="presentation">
        <div class="detail-dialog" role="dialog" aria-modal="true" aria-label="${this._esc(this._detailTitle(item))}">
          <div class="detail-head">
            <h3>${this._esc(this._detailTitle(item))}</h3>
            <button type="button" class="detail-close" data-action="detail-close" title="Schließen" aria-label="Schließen">
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>
          <div class="detail-scroll">${this._renderDetailBody(item, dateLabel)}</div>
        </div>
      </div>`;
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
      const tag = planned
        ? `<button type="button" class="meal-tile planned" data-action="show-detail" data-type="${this._esc(meal.entry_type)}" title="${this._esc(meal.name)} – Details anzeigen">`
        : `<article class="meal-tile empty">`;
      const endTag = planned ? `</button>` : `</article>`;
      return `
        ${tag}
          <div class="meal-media">${media}</div>
          <div class="meal-body">
            <span class="meal-label"><ha-icon icon="${this._esc(meal.icon || "mdi:food")}"></ha-icon>${this._esc(meal.label)}</span>
            ${time ? `<span class="meal-time">${this._esc(time)}</span>` : ""}
            ${body}
          </div>
        ${endTag}`;
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
          display: block; width: 100%; text-align: left; font: inherit;
        }
        button.meal-tile {
          cursor: pointer; padding: 0; transition: box-shadow .15s, transform .1s;
        }
        button.meal-tile:hover { box-shadow: 0 4px 16px rgba(0,0,0,.1); }
        button.meal-tile:active { transform: scale(0.99); }
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
        .detail-overlay {
          position: fixed; inset: 0; z-index: 200;
          background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center;
          padding: 16px; box-sizing: border-box;
        }
        .detail-dialog {
          width: min(560px, 100%); max-height: min(88vh, 720px);
          background: var(--card-background-color, #fff);
          border-radius: 16px; box-shadow: 0 12px 40px rgba(0,0,0,.28);
          display: flex; flex-direction: column; overflow: hidden;
        }
        .detail-head {
          display: flex; align-items: center; justify-content: space-between; gap: 12px;
          padding: 14px 16px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.1));
        }
        .detail-head h3 {
          margin: 0; font-size: 1rem; font-weight: 600;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .detail-close {
          border: none; background: transparent; cursor: pointer; border-radius: 50%;
          width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center;
          color: var(--primary-text-color); flex-shrink: 0;
        }
        .detail-close:hover { background: var(--secondary-background-color, rgba(0,0,0,.06)); }
        .detail-close ha-icon { --mdc-icon-size: 22px; }
        .detail-scroll { overflow-y: auto; flex: 1; padding: 0; }
        .detail-loading { display: flex; justify-content: center; padding: 40px 0; }
        .detail-hero { aspect-ratio: 16/9; max-height: 220px; overflow: hidden; background: var(--secondary-background-color, #eee); }
        .detail-img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .detail-img.placeholder {
          width: 100%; height: 100%; min-height: 140px;
          display: flex; align-items: center; justify-content: center;
          color: var(--primary-color);
        }
        .detail-img.placeholder ha-icon { --mdc-icon-size: 48px; opacity: .7; }
        .detail-content { padding: 16px 18px 20px; }
        .detail-meta {
          display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center;
          margin: 0 0 10px; font-size: 0.8rem; color: var(--secondary-text-color);
        }
        .meal-badge {
          display: inline-flex; align-items: center; gap: 4px; font-weight: 600;
          color: var(--primary-color);
        }
        .meal-badge ha-icon { --mdc-icon-size: 16px; }
        .detail-title { margin: 0 0 10px; font-size: 1.25rem; line-height: 1.3; }
        .detail-desc { margin: 0 0 12px; line-height: 1.5; }
        .meta-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .meta-chip {
          display: inline-flex; align-items: center; gap: 4px;
          font-size: 0.78rem; padding: 4px 10px; border-radius: 999px;
          background: var(--secondary-background-color, #f0f0f0);
          color: var(--secondary-text-color);
        }
        .meta-chip ha-icon { --mdc-icon-size: 14px; }
        .source-link { display: inline-block; margin-bottom: 14px; font-size: 0.85rem; color: var(--primary-color); }
        .detail-sections { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
        @media (max-width: 520px) { .detail-sections { grid-template-columns: 1fr; } }
        .detail-panel {
          padding: 12px; border-radius: 10px;
          background: var(--secondary-background-color, rgba(0,0,0,.04));
        }
        .detail-panel h4 {
          margin: 0 0 8px; font-size: 0.85rem; display: flex; align-items: center; gap: 6px;
        }
        .detail-panel h4 ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
        .ingredient-list, .step-list { margin: 0; padding-left: 1.2rem; font-size: 0.88rem; line-height: 1.45; }
        .step-list { list-style: none; padding-left: 0; }
        .step-list li { display: flex; gap: 10px; margin-bottom: 10px; }
        .step-num {
          flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%;
          background: var(--primary-color); color: #fff;
          font-size: 0.72rem; font-weight: 700;
          display: inline-flex; align-items: center; justify-content: center;
        }
        .muted { color: var(--secondary-text-color); font-style: italic; }
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
      </ha-card>
      ${this._renderDetailOverlay(view.date_label)}`;
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
  description: "Essensplan mit Tag-Navigation – Klick zeigt Rezeptdetails",
  preview: true,
  documentationURL: "https://github.com/sulmaring-tech/essensplaner",
});
