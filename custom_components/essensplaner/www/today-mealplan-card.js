/* Essensplaner – Lovelace card: today's meal plan with images */

class TodayMealplanCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((id) =>
      id.startsWith("sensor.") && id.endsWith("_mealplan_today")
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

  set hass(hass) {
    this._hass = hass;
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

  _render() {
    if (!this._config || !this._hass) return;

    const state = this._hass.states[this._config.entity];
    if (!state) {
      this.innerHTML = `
        <ha-card header="Essensplan heute">
          <div class="card-content error">Entity nicht gefunden: ${this._esc(this._config.entity)}</div>
        </ha-card>`;
      return;
    }

    const attrs = state.attributes || {};
    const meals = attrs.meals || [];
    const dateLabel = attrs.date_label || attrs.date || "";
    const title = this._config.title || "Essensplan heute";

    const tiles = meals.map((meal) => {
      const planned = meal.planned && meal.name;
      const time =
        meal.start_time && meal.end_time
          ? `${meal.start_time}–${meal.end_time}`
          : "";
      const media = planned && meal.image_url
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

    this.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .wrap { padding: 12px 16px 16px; }
        .head {
          display: flex; align-items: baseline; justify-content: space-between;
          gap: 12px; margin-bottom: 14px; flex-wrap: wrap;
        }
        .head h2 {
          margin: 0; font-size: 1.1rem; font-weight: 600;
          color: var(--primary-text-color);
        }
        .date { font-size: 0.85rem; color: var(--secondary-text-color); }
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
        .error { padding: 16px; color: var(--error-color, #f44336); }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="head">
            <h2>${this._esc(title)}</h2>
            <span class="date">${this._esc(dateLabel)}</span>
          </div>
          <div class="grid">${tiles}</div>
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
  name: "Essensplan Heute",
  description: "Heutiger Essensplan mit Rezeptbildern",
  preview: true,
  documentationURL: "https://github.com/sulmaring-tech/essensplaner",
});
