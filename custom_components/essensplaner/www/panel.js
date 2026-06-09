/* Essensplaner – Home Assistant Sidebar Panel */

const MEALS = [
  { id: "breakfast", label: "Frühstück", icon: "mdi:coffee" },
  { id: "lunch", label: "Mittagessen", icon: "mdi:silverware-fork-knife" },
  { id: "dinner", label: "Abendessen", icon: "mdi:food-turkey" },
];

class PanelEssensplaner extends HTMLElement {
  constructor() {
    super();
    this._tab = "recipes";
    this._entryId = null;
    this._recipes = [];
    this._mealplan = [];
    this._selected = null;
    this._mode = "view"; // view | create | edit
    this._search = "";
    this._importUrl = "";
    this._loading = false;
    this._toast = "";
    this._weekOffset = 0;
    this._dialog = null; // { date, type, label }
    this._dialogSearch = "";
    this._toastTimer = null;
    this._searchTimer = null;
    this._onClick = this._handleClick.bind(this);
    this._onInput = this._handleInput.bind(this);
    this._onChange = this._handleChange.bind(this);
  }

  connectedCallback() {
    this.addEventListener("click", this._onClick);
    this.addEventListener("input", this._onInput);
    this.addEventListener("change", this._onChange);
  }

  disconnectedCallback() {
    this.removeEventListener("click", this._onClick);
    this.removeEventListener("input", this._onInput);
    this.removeEventListener("change", this._onChange);
    clearTimeout(this._toastTimer);
    clearTimeout(this._searchTimer);
  }

  set hass(hass) {
    const hadEntry = !!this._entryId;
    this._hass = hass;
    const entries = this._entries();
    if (!this._entryId && entries.length) {
      this._entryId = entries[0].entry_id;
    }
    if (this._entryId && !hadEntry) {
      this._load();
    } else {
      this._paint();
    }
  }

  set narrow(v) { this._narrow = v; }
  set route(v) { this._route = v; }
  set panel(v) { this._panel = v; }

  /* ── data ─────────────────────────────────────────── */

  _entries() {
    const raw = this._hass?.configEntries;
    if (!raw) return [];
    const list = Array.isArray(raw) ? raw : Object.values(raw);
    return list.filter((e) => e.domain === "essensplaner");
  }

  async _svc(service, data = {}) {
    if (!this._entryId) throw new Error("Kein Haushalt konfiguriert");
    const res = await this._hass.callService(
      "essensplaner", service,
      { config_entry_id: this._entryId, ...data },
      undefined, true
    );
    return res?.response ?? res;
  }

  async _load() {
    if (!this._entryId) return;
    this._loading = true;
    this._paint();
    try {
      const range = this._weekRange();
      const [r, m] = await Promise.all([
        this._svc("get_recipes", { result_limit: 500 }),
        this._svc("get_mealplan", { start_date: range.start, end_date: range.end }),
      ]);
      this._recipes = r?.recipes || [];
      this._mealplan = m?.mealplan || [];
    } catch (e) {
      this._notify("Fehler beim Laden: " + (e.message || e), true);
    }
    this._loading = false;
    this._paint();
  }

  async _reloadPlan() {
    const range = this._weekRange();
    const m = await this._svc("get_mealplan", { start_date: range.start, end_date: range.end });
    this._mealplan = m?.mealplan || [];
    this._paint();
  }

  /* ── helpers ──────────────────────────────────────── */

  _esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  _notify(msg, error = false) {
    this._toast = { msg, error };
    this._paint();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { this._toast = null; this._paint(); }, 4000);
  }

  _today() {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    return d;
  }

  _weekRange() {
    const start = this._today();
    start.setDate(start.getDate() + this._weekOffset * 7);
    const monday = new Date(start);
    const day = monday.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    monday.setDate(monday.getDate() + diff);
    const end = new Date(monday);
    end.setDate(end.getDate() + 6);
    return {
      start: monday.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
      days: Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday);
        d.setDate(d.getDate() + i);
        return d.toISOString().slice(0, 10);
      }),
      monday, end,
    };
  }

  _fmtDay(iso) {
    const d = new Date(iso + "T12:00:00");
    const wd = d.toLocaleDateString("de-DE", { weekday: "long" });
    const dm = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
    const today = new Date().toISOString().slice(0, 10);
    return { wd, dm, today: iso === today };
  }

  _filtered() {
    if (!this._search) return this._recipes;
    const q = this._search.toLowerCase();
    return this._recipes.filter((r) =>
      [r.name, r.description, ...(r.tags || []), ...(r.categories || [])]
        .join(" ").toLowerCase().includes(q)
    );
  }

  _plan(date, type) {
    return this._mealplan.find((m) => m.date === date && m.entry_type === type);
  }

  _planName(p) {
    if (!p) return null;
    return p.recipe?.name || p.title || null;
  }

  _mealLabel(id) {
    return MEALS.find((m) => m.id === id)?.label || id;
  }

  _formVal(field) {
    return this.querySelector(`[name="${field}"]`)?.value ?? "";
  }

  /* ── actions ──────────────────────────────────────── */

  async _import() {
    const url = this._importUrl.trim();
    if (!url) return;
    this._loading = true;
    this._paint();
    try {
      await this._svc("import_recipe", { url });
      this._importUrl = "";
      this._notify("Rezept importiert");
      await this._load();
    } catch (e) {
      this._loading = false;
      this._notify("Import fehlgeschlagen: " + (e.message || e), true);
      this._paint();
    }
  }

  async _saveRecipe() {
    const name = this._formVal("name").trim();
    if (!name) { this._notify("Bitte einen Namen eingeben", true); return; }
    const payload = {
      name,
      description: this._formVal("description").trim(),
      ingredients: this._formVal("ingredients").split("\n").map((s) => s.trim()).filter(Boolean),
      instructions: this._formVal("instructions").split("\n").map((s) => s.trim()).filter(Boolean),
    };
    this._loading = true;
    this._paint();
    try {
      if (this._mode === "edit" && this._selected) {
        await this._svc("update_recipe", { recipe_id: this._selected.id, ...payload });
        this._notify("Rezept gespeichert");
      } else {
        await this._svc("create_recipe", payload);
        this._notify("Rezept erstellt");
      }
      this._mode = "view";
      this._selected = null;
      await this._load();
    } catch (e) {
      this._loading = false;
      this._notify("Speichern fehlgeschlagen: " + (e.message || e), true);
      this._paint();
    }
  }

  async _deleteRecipe(id) {
    if (!confirm("Rezept wirklich löschen?")) return;
    try {
      await this._svc("delete_recipe", { recipe_id: id });
      this._selected = null;
      this._notify("Rezept gelöscht");
      await this._load();
    } catch (e) {
      this._notify("Löschen fehlgeschlagen: " + (e.message || e), true);
    }
  }

  async _assignPlan(recipeId) {
    if (!this._dialog) return;
    try {
      await this._svc("set_mealplan", {
        date: this._dialog.date,
        entry_type: this._dialog.type,
        recipe_id: recipeId,
      });
      this._dialog = null;
      this._notify("Gericht geplant");
      await this._reloadPlan();
    } catch (e) {
      this._notify("Planen fehlgeschlagen: " + (e.message || e), true);
    }
  }

  async _clearPlan() {
    if (!this._dialog) return;
    try {
      await this._svc("clear_mealplan", {
        date: this._dialog.date,
        entry_type: this._dialog.type,
      });
      this._dialog = null;
      this._notify("Eintrag entfernt");
      await this._reloadPlan();
    } catch (e) {
      this._notify("Entfernen fehlgeschlagen: " + (e.message || e), true);
    }
  }

  async _addShopping(id) {
    try {
      await this._svc("add_recipe_to_shopping_list", { recipe_id: id });
      this._notify("Zutaten zur Einkaufsliste hinzugefügt");
    } catch (e) {
      this._notify(e.message || String(e), true);
    }
  }

  /* ── events ───────────────────────────────────────── */

  _handleInput(ev) {
    const el = ev.target;
    if (el.id === "import-url") { this._importUrl = el.value; return; }
    if (el.id === "search") {
      this._search = el.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => this._paint(), 200);
      return;
    }
    if (el.id === "dialog-search") {
      this._dialogSearch = el.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => this._paint(), 150);
    }
  }

  async _handleChange(ev) {
    if (ev.target.id === "entry-select") {
      this._entryId = ev.target.value;
      this._selected = null;
      this._mode = "view";
      await this._load();
    }
  }

  async _handleClick(ev) {
    const t = ev.target.closest("[data-a]");
    if (!t) {
      if (ev.target.classList.contains("overlay")) {
        this._dialog = null;
        this._paint();
      }
      return;
    }
    const a = t.dataset.a;

    if (a === "tab") { this._tab = t.dataset.tab; this._paint(); return; }
    if (a === "reload") { await this._load(); return; }
    if (a === "import") { await this._import(); return; }
    if (a === "new") { this._selected = null; this._mode = "create"; this._paint(); return; }
    if (a === "select") {
      this._selected = this._recipes.find((r) => r.id === t.dataset.id) || null;
      this._mode = "view";
      this._paint();
      return;
    }
    if (a === "edit") { this._mode = "edit"; this._paint(); return; }
    if (a === "cancel") { this._mode = "view"; this._paint(); return; }
    if (a === "save") { await this._saveRecipe(); return; }
    if (a === "delete") { await this._deleteRecipe(t.dataset.id); return; }
    if (a === "shop") { await this._addShopping(t.dataset.id); return; }
    if (a === "week-prev") { this._weekOffset--; await this._reloadPlan(); return; }
    if (a === "week-next") { this._weekOffset++; await this._reloadPlan(); return; }
    if (a === "week-today") { this._weekOffset = 0; await this._reloadPlan(); return; }
    if (a === "plan-cell") {
      this._dialog = { date: t.dataset.date, type: t.dataset.type, label: this._mealLabel(t.dataset.type) };
      this._dialogSearch = "";
      this._paint();
      return;
    }
    if (a === "plan-pick") { await this._assignPlan(t.dataset.id); return; }
    if (a === "plan-clear") { await this._clearPlan(); return; }
    if (a === "dialog-close") { this._dialog = null; this._paint(); return; }
  }

  /* ── render blocks ────────────────────────────────── */

  _renderForm(r) {
    const data = r || { name: "", description: "", ingredients: [], instructions: [] };
    const title = this._mode === "edit" ? "Rezept bearbeiten" : "Neues Rezept";
    return `
      <div class="form-card">
        <h3>${title}</h3>
        <label>Name<input class="inp" name="name" value="${this._esc(data.name)}" autofocus></label>
        <label>Beschreibung<textarea class="inp" name="description" rows="2">${this._esc(data.description || "")}</textarea></label>
        <label>Zutaten <span class="hint">(eine pro Zeile)</span>
          <textarea class="inp" name="ingredients" rows="6">${this._esc((data.ingredients || []).map((i) => i.name || i).join("\n"))}</textarea></label>
        <label>Zubereitung <span class="hint">(ein Schritt pro Zeile)</span>
          <textarea class="inp" name="instructions" rows="6">${this._esc((data.instructions || []).join("\n"))}</textarea></label>
        <div class="btn-row">
          <button class="btn primary" data-a="save">Speichern</button>
          <button class="btn" data-a="cancel">Abbrechen</button>
        </div>
      </div>`;
  }

  _renderRecipeDetail() {
    if (this._mode === "create" || this._mode === "edit") {
      return this._renderForm(this._mode === "edit" ? this._selected : null);
    }
    const r = this._selected;
    if (!r) {
      return `<div class="empty-detail">
        <ha-icon icon="mdi:book-open-page-variant"></ha-icon>
        <p>Rezept aus der Liste wählen oder neu anlegen</p>
      </div>`;
    }
    const ings = (r.ingredients || []).map((i) => `<li>${this._esc(i.name || i)}</li>`).join("");
    const steps = (r.instructions || []).map((s) => `<li>${this._esc(s)}</li>`).join("");
    return `
      <div class="detail-card">
        <h2>${this._esc(r.name)}</h2>
        ${r.description ? `<p class="desc">${this._esc(r.description)}</p>` : ""}
        <section><h4>Zutaten</h4><ul>${ings || "<li class='muted'>–</li>"}</ul></section>
        <section><h4>Zubereitung</h4><ol>${steps || "<li class='muted'>–</li>"}</ol></section>
        <div class="btn-row">
          <button class="btn" data-a="edit">Bearbeiten</button>
          <button class="btn" data-a="shop" data-id="${r.id}">Zur Einkaufsliste</button>
          <button class="btn danger" data-a="delete" data-id="${r.id}">Löschen</button>
        </div>
      </div>`;
  }

  _renderRecipesTab() {
    const list = this._filtered();
    const cards = list.length
      ? list.map((r) => `
          <div class="recipe-card ${this._selected?.id === r.id ? "on" : ""}" data-a="select" data-id="${r.id}">
            <ha-icon icon="mdi:food"></ha-icon>
            <div class="rc-body">
              <strong>${this._esc(r.name)}</strong>
              ${r.description ? `<span>${this._esc(r.description).slice(0, 60)}</span>` : ""}
            </div>
          </div>`).join("")
      : `<p class="muted center">Noch keine Rezepte – URL importieren oder „Neues Rezept“.</p>`;

    return `
      <div class="import-bar">
        <input class="inp grow" id="import-url" placeholder="Rezept-URL einfügen (z. B. Chefkoch)…" value="${this._esc(this._importUrl)}">
        <button class="btn primary" data-a="import">Importieren</button>
        <button class="btn" data-a="new">+ Neues Rezept</button>
      </div>
      <div class="toolbar">
        <input class="inp" id="search" placeholder="Rezepte suchen…" value="${this._esc(this._search)}">
        <span class="badge">${list.length} Rezepte</span>
      </div>
      <div class="split">
        <div class="recipe-list">${cards}</div>
        <div class="recipe-detail">${this._renderRecipeDetail()}</div>
      </div>`;
  }

  _renderPlanTab() {
    const { days, monday, end } = this._weekRange();
    const weekLabel = `${monday.toLocaleDateString("de-DE", { day: "2-digit", month: "short" })} – ${end.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" })}`;

    const head = MEALS.map((m) => `<th><ha-icon icon="${m.icon}"></ha-icon> ${m.label}</th>`).join("");
    const rows = days.map((day) => {
      const { wd, dm, today } = this._fmtDay(day);
      const cells = MEALS.map((m) => {
        const p = this._plan(day, m.id);
        const name = this._planName(p);
        return `
          <td>
            <button class="plan-cell ${name ? "filled" : ""} ${today ? "today-col" : ""}" data-a="plan-cell" data-date="${day}" data-type="${m.id}">
              ${name ? `<span class="plan-name">${this._esc(name)}</span>` : `<span class="plan-empty">+ Zuweisen</span>`}
            </button>
          </td>`;
      }).join("");
      return `<tr class="${today ? "today-row" : ""}"><td class="day-label"><strong>${wd}</strong><br>${dm}</td>${cells}</tr>`;
    }).join("");

    return `
      <div class="week-nav">
        <button class="btn icon" data-a="week-prev"><ha-icon icon="mdi:chevron-left"></ha-icon></button>
        <span class="week-label">${weekLabel}</span>
        <button class="btn icon" data-a="week-next"><ha-icon icon="mdi:chevron-right"></ha-icon></button>
        <button class="btn" data-a="week-today">Heute</button>
      </div>
      <div class="plan-wrap">
        <table class="plan-grid">
          <thead><tr><th></th>${head}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  _renderDialog() {
    if (!this._dialog) return "";
    const { date, type, label } = this._dialog;
    const { wd, dm } = this._fmtDay(date);
    const current = this._planName(this._plan(date, type));
    const q = (this._dialogSearch || "").toLowerCase();
    const picks = this._recipes.filter((r) => !q || r.name.toLowerCase().includes(q));

    const list = picks.length
      ? picks.map((r) => `
          <button class="pick-item" data-a="plan-pick" data-id="${r.id}">
            <ha-icon icon="mdi:food"></ha-icon>
            <span>${this._esc(r.name)}</span>
          </button>`).join("")
      : `<p class="muted">Kein Rezept gefunden</p>`;

    return `
      <div class="overlay">
        <div class="dialog" onclick="event.stopPropagation()">
          <div class="dialog-head">
            <h3>${label}</h3>
            <span class="muted">${wd}, ${dm}</span>
            <button class="btn icon close" data-a="dialog-close"><ha-icon icon="mdi:close"></ha-icon></button>
          </div>
          ${current ? `<div class="current-plan">Aktuell: <strong>${this._esc(current)}</strong></div>` : ""}
          <input class="inp" id="dialog-search" placeholder="Rezept wählen…" value="${this._esc(this._dialogSearch)}">
          <div class="pick-list">${list}</div>
          <div class="btn-row">
            ${current ? `<button class="btn danger" data-a="plan-clear">Entfernen</button>` : ""}
            <button class="btn" data-a="dialog-close">Abbrechen</button>
          </div>
        </div>
      </div>`;
  }

  _paint() {
    if (!this._hass) return;
    const entries = this._entries();
    const sel = entries.length > 1
      ? `<select id="entry-select" class="inp">${entries.map((e) =>
          `<option value="${e.entry_id}" ${e.entry_id === this._entryId ? "selected" : ""}>${this._esc(e.title || e.entry_id)}</option>`
        ).join("")}</select>`
      : "";

    let body = "";
    if (!entries.length) {
      body = `<div class="alert">Bitte Essensplaner unter <em>Einstellungen → Integrationen</em> einrichten.</div>`;
    } else if (this._loading) {
      body = `<div class="loading"><ha-circular-progress active></ha-circular-progress></div>`;
    } else if (this._tab === "recipes") {
      body = this._renderRecipesTab();
    } else {
      body = this._renderPlanTab();
    }

    const toast = this._toast
      ? `<div class="toast ${this._toast.error ? "err" : ""}">${this._esc(this._toast.msg)}</div>`
      : "";

    this.innerHTML = `
      <style>${PanelEssensplaner._CSS}</style>
      <header class="top">
        <div class="brand"><ha-icon icon="mdi:food"></ha-icon><h1>Essensplaner</h1></div>
        <div class="top-actions">${sel}<button class="btn icon" data-a="reload" title="Aktualisieren"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
      </header>
      <nav class="tabs">
        <button class="tab ${this._tab === "recipes" ? "on" : ""}" data-a="tab" data-tab="recipes">Rezepte</button>
        <button class="tab ${this._tab === "plan" ? "on" : ""}" data-a="tab" data-tab="plan">Essensplan</button>
      </nav>
      <main class="content">${body}</main>
      ${toast}
      ${this._renderDialog()}`;
  }
}

PanelEssensplaner._CSS = `
  :host {
    display: block;
    min-height: 100%;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--ha-font-family, Roboto, sans-serif);
  }
  * { box-sizing: border-box; }
  .top {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; background: var(--card-background-color, #fff);
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    position: sticky; top: 0; z-index: 10;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand h1 { margin: 0; font-size: 1.35rem; font-weight: 500; }
  .brand ha-icon { color: var(--primary-color); --mdc-icon-size: 28px; }
  .top-actions { display: flex; gap: 8px; align-items: center; }
  .tabs {
    display: flex; gap: 4px; padding: 12px 24px 0;
    background: var(--card-background-color, #fff);
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .tab {
    padding: 10px 20px; border: none; background: none; cursor: pointer;
    font-size: 0.95rem; color: var(--secondary-text-color);
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .tab.on { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 500; }
  .content { padding: 20px 24px 40px; max-width: 1280px; margin: 0 auto; }
  .inp {
    padding: 10px 12px; border: 1px solid var(--divider-color, #ccc);
    border-radius: 8px; background: var(--card-background-color, #fff);
    color: inherit; font: inherit; width: 100%;
  }
  .inp:focus { outline: 2px solid var(--primary-color); border-color: transparent; }
  .grow { flex: 1; min-width: 200px; }
  .btn {
    padding: 9px 16px; border-radius: 8px; border: 1px solid var(--divider-color, #ccc);
    background: var(--card-background-color, #fff); color: inherit;
    cursor: pointer; font: inherit; white-space: nowrap;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .btn:hover { background: var(--secondary-background-color, #f5f5f5); }
  .btn.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .btn.primary:hover { filter: brightness(1.08); }
  .btn.danger { color: var(--error-color, #f44336); border-color: var(--error-color, #f44336); }
  .btn.icon { padding: 8px; }
  .btn-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .import-bar, .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; }
  .badge {
    padding: 4px 10px; border-radius: 12px; font-size: 0.85rem;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
  }
  .split { display: grid; grid-template-columns: 340px 1fr; gap: 20px; min-height: 480px; }
  @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
  .recipe-list {
    display: flex; flex-direction: column; gap: 6px;
    max-height: 70vh; overflow-y: auto; padding-right: 4px;
  }
  .recipe-card {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 12px 14px; border-radius: 10px; cursor: pointer;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #e8e8e8);
    transition: border-color .15s, box-shadow .15s;
  }
  .recipe-card:hover { border-color: var(--primary-color); box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .recipe-card.on { border-color: var(--primary-color); background: var(--secondary-background-color, #f0f7ff); }
  .recipe-card ha-icon { color: var(--primary-color); flex-shrink: 0; margin-top: 2px; }
  .rc-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .rc-body strong { font-size: 0.95rem; }
  .rc-body span { font-size: 0.82rem; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .detail-card, .form-card {
    background: var(--card-background-color, #fff);
    border-radius: 12px; padding: 24px;
    border: 1px solid var(--divider-color, #e8e8e8);
    box-shadow: 0 1px 4px rgba(0,0,0,.04);
  }
  .detail-card h2, .form-card h3 { margin: 0 0 12px; }
  .desc { color: var(--secondary-text-color); line-height: 1.5; }
  .detail-card section { margin-top: 20px; }
  .detail-card h4 { margin: 0 0 8px; font-size: 0.9rem; text-transform: uppercase; letter-spacing: .04em; color: var(--secondary-text-color); }
  .detail-card ul, .detail-card ol { margin: 0; padding-left: 20px; line-height: 1.6; }
  .form-card label { display: block; margin-bottom: 14px; font-size: 0.9rem; font-weight: 500; }
  .form-card textarea { resize: vertical; }
  .hint { font-weight: 400; color: var(--secondary-text-color); font-size: 0.8rem; }
  .empty-detail {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; min-height: 300px; color: var(--secondary-text-color); text-align: center; gap: 12px;
  }
  .empty-detail ha-icon { --mdc-icon-size: 48px; opacity: .4; }
  .week-nav {
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;
  }
  .week-label { font-weight: 500; font-size: 1.05rem; min-width: 180px; text-align: center; }
  .plan-wrap { overflow-x: auto; border-radius: 12px; border: 1px solid var(--divider-color, #e8e8e8); background: var(--card-background-color, #fff); }
  .plan-grid { width: 100%; border-collapse: collapse; min-width: 640px; }
  .plan-grid th, .plan-grid td { padding: 0; border: 1px solid var(--divider-color, #eee); vertical-align: top; }
  .plan-grid th {
    padding: 12px 8px; font-size: 0.85rem; font-weight: 500;
    background: var(--secondary-background-color, #f5f5f5);
    text-align: center;
  }
  .plan-grid th ha-icon { vertical-align: middle; margin-right: 4px; --mdc-icon-size: 18px; }
  .day-label { padding: 12px 14px !important; font-size: 0.85rem; white-space: nowrap; background: var(--secondary-background-color, #fafafa); }
  .today-row .day-label { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
  .plan-cell {
    width: 100%; min-height: 72px; padding: 12px; border: none; background: transparent;
    cursor: pointer; text-align: left; font: inherit; color: inherit;
    transition: background .12s;
  }
  .plan-cell:hover { background: var(--secondary-background-color, #f5f5f5); }
  .plan-cell.filled { background: color-mix(in srgb, var(--primary-color) 8%, var(--card-background-color, #fff)); }
  .plan-cell.today-col.filled { background: color-mix(in srgb, var(--primary-color) 14%, var(--card-background-color, #fff)); }
  .plan-name { font-size: 0.88rem; font-weight: 500; line-height: 1.35; display: block; }
  .plan-empty { font-size: 0.82rem; color: var(--secondary-text-color); }
  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.45);
    display: flex; align-items: center; justify-content: center;
    z-index: 100; padding: 16px;
  }
  .dialog {
    background: var(--card-background-color, #fff);
    border-radius: 14px; width: 100%; max-width: 420px;
    max-height: 80vh; display: flex; flex-direction: column;
    box-shadow: 0 12px 40px rgba(0,0,0,.2); padding: 20px;
  }
  .dialog-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; }
  .dialog-head h3 { margin: 0; flex: 1; }
  .dialog-head .close { margin-left: auto; }
  .current-plan { padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); margin-bottom: 12px; font-size: 0.9rem; }
  .pick-list { overflow-y: auto; flex: 1; margin: 12px 0; display: flex; flex-direction: column; gap: 4px; max-height: 40vh; }
  .pick-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border: 1px solid var(--divider-color, #eee); border-radius: 8px;
    background: none; cursor: pointer; font: inherit; text-align: left; width: 100%;
  }
  .pick-item:hover { border-color: var(--primary-color); background: var(--secondary-background-color); }
  .toast {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    padding: 12px 20px; border-radius: 10px; z-index: 200;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    box-shadow: 0 4px 16px rgba(0,0,0,.15); font-size: 0.9rem;
  }
  .toast.err { background: var(--error-color, #f44336); }
  .loading { text-align: center; padding: 60px; }
  .muted { color: var(--secondary-text-color); }
  .center { text-align: center; padding: 24px; }
  .alert { padding: 20px; border-radius: 10px; background: var(--warning-color, #fff3e0); }
`;

customElements.define("panel-essensplaner", PanelEssensplaner);
