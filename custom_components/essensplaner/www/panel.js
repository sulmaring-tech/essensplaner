/* Essensplaner – Home Assistant Sidebar Panel */

const MEALS = [
  { id: "breakfast", label: "Frühstück", icon: "mdi:coffee" },
  { id: "lunch", label: "Mittagessen", icon: "mdi:silverware-fork-knife" },
  { id: "dinner", label: "Abendessen", icon: "mdi:food-turkey" },
];

const MEAL_TAG_IDS = new Set(MEALS.map((m) => m.id));

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
    this._mealFilter = null;
    this._importUrl = "";
    this._loading = false;
    this._toast = "";
    this._weekOffset = 0;
    this._dialog = null; // { date, type, label }
    this._dialogSearch = "";
    this._toastTimer = null;
    this._searchTimer = null;
    this._cachedEntries = [];
    this._entriesLoading = false;
    this._formDraft = null;
    this._mealTimes = {};
    this._mealTimesOpen = false;
    this._inspirationQuery = "";
    this._inspirationResults = [];
    this._inspirationLoading = false;
    this._inspirationOpen = false;
    this._dialogShowAll = false;
    this._onlinePreview = null;
    this._onlineImporting = false;
    this._dataLoaded = false;
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
    this._hass = hass;
    this._mergeEntries(this._panel?.config?.entries);
    this._ensureEntryId();
    if (this._entryId && !this._dataLoaded && !this._loading) {
      this._load();
    } else if (!this._entryId && !this._entriesLoading) {
      this._fetchEntries().then(() => this._paint());
    } else if (!this._isEditing()) {
      this._paint();
    }
  }

  _isEditing() {
    return (
      this._mode === "create" ||
      this._mode === "edit" ||
      !!this._dialog ||
      this._mealTimesOpen ||
      this._inspirationOpen ||
      !!this._onlinePreview
    );
  }

  _isRecipeModalOpen() {
    return this._mode === "create" || this._mode === "edit" || (this._mode === "view" && !!this._selected);
  }

  _closeRecipeModal() {
    this._formDraft = null;
    this._mode = "view";
    this._selected = null;
  }

  _clickTarget(ev) {
    for (const el of ev.composedPath()) {
      if (el instanceof HTMLElement && el.dataset?.a) return el;
    }
    return null;
  }

  set narrow(v) { this._narrow = v; }
  set route(v) { this._route = v; }
  set panel(v) {
    this._panel = v;
    this._mergeEntries(v?.config?.entries);
    this._ensureEntryId();
    if (this._hass && this._entryId && !this._dataLoaded) this._load();
  }

  _ensureEntryId() {
    if (this._entryId) return;
    const entries = this._entries();
    if (entries.length) this._entryId = entries[0].entry_id;
  }

  /* ── data ─────────────────────────────────────────── */

  _mergeEntries(list) {
    if (!list?.length) return;
    const byId = new Map(this._cachedEntries.map((e) => [e.entry_id, e]));
    for (const e of list) {
      const id = e.entry_id || e.entryId;
      if (id) byId.set(id, { entry_id: id, title: e.title || id });
    }
    this._cachedEntries = [...byId.values()];
  }

  _entries() {
    if (this._cachedEntries.length) return this._cachedEntries;
    const fromEntities = this._entriesFromEntities();
    if (fromEntities.length) return fromEntities;
    const raw = this._hass?.configEntries;
    if (!raw) return [];
    if (Array.isArray(raw)) {
      return raw
        .filter((e) => e.domain === "essensplaner")
        .map((e) => ({ entry_id: e.entry_id || e.entryId, title: e.title || e.entry_id }));
    }
    return Object.entries(raw)
      .filter(([, e]) => e?.domain === "essensplaner")
      .map(([id, e]) => ({
        entry_id: e.entry_id || e.entryId || id,
        title: e.title || id,
      }));
  }

  _entriesFromEntities() {
    const entities = this._hass?.entities;
    if (!entities) return [];
    const map = new Map();
    for (const entity of Object.values(entities)) {
      if (entity?.platform === "essensplaner" && entity?.config_entry_id) {
        map.set(entity.config_entry_id, {
          entry_id: entity.config_entry_id,
          title: entity.config_entry_id,
        });
      }
    }
    return [...map.values()];
  }

  async _fetchEntries() {
    if (!this._hass || this._entriesLoading) return;
    this._entriesLoading = true;
    try {
      const res = await this._hass.callWS({ type: "essensplaner/config_entries" });
      this._mergeEntries(res);
      if (!this._entryId && this._cachedEntries.length) {
        this._entryId = this._cachedEntries[0].entry_id;
        await this._load();
        return;
      }
    } catch (e) {
      console.warn("Essensplaner: config entries via WS failed", e);
    } finally {
      this._entriesLoading = false;
    }
  }

  _unwrapService(res) {
    if (!res) return null;
    if (res.response !== undefined) return res.response;
    if (res.service_response !== undefined) return res.service_response;
    return res;
  }

  _extractRecipes(data) {
    const body = this._unwrapService(data);
    if (Array.isArray(body)) return body;
    if (Array.isArray(body?.recipes)) return body.recipes;
    return [];
  }

  _extractMealplan(data) {
    const body = this._unwrapService(data);
    if (Array.isArray(body)) return body;
    if (Array.isArray(body?.mealplan)) return body.mealplan;
    return [];
  }

  async _svc(service, data = {}, returnResponse = true) {
    if (!this._entryId) throw new Error("Kein Haushalt konfiguriert");
    const res = await this._hass.callService(
      "essensplaner", service,
      { config_entry_id: this._entryId, ...data },
      undefined,
      true,
      returnResponse
    );
    return returnResponse ? this._unwrapService(res) : res;
  }

  async _load() {
    if (!this._entryId) return;
    this._loading = true;
    this._paint();
    try {
      const r = await this._svc("get_recipes", { result_limit: 100 });
      this._recipes = this._extractRecipes(r);
    } catch (e) {
      this._notify("Rezepte laden fehlgeschlagen: " + (e.message || e), true);
    }
    try {
      const range = this._weekRange();
      const m = await this._svc("get_mealplan", {
        start_date: range.start,
        end_date: range.end,
      });
      this._mealplan = this._extractMealplan(m);
    } catch (e) {
      this._notify("Essensplan laden fehlgeschlagen: " + (e.message || e), true);
    }
    await this._loadMealTimes();
    this._dataLoaded = true;
    this._loading = false;
    this._paint();
  }

  async _reloadPlan() {
    const range = this._weekRange();
    const m = await this._svc("get_mealplan", { start_date: range.start, end_date: range.end });
    this._mealplan = this._extractMealplan(m);
    this._paint();
  }

  /* ── helpers ──────────────────────────────────────── */

  _esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  _notify(msg, error = false) {
    this._toast = { msg, error };
    if (this._isEditing()) {
      this._updateToast();
    } else {
      this._paint();
    }
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      if (this._isEditing()) this._updateToast();
      else this._paint();
    }, 4000);
  }

  _updateToast() {
    let el = this.querySelector(".toast");
    if (!this._toast) {
      el?.remove();
      return;
    }
    if (!el) {
      el = document.createElement("div");
      this.appendChild(el);
    }
    el.className = `toast ${this._toast.error ? "err" : ""}`;
    el.textContent = this._toast.msg;
  }

  _today() {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    return d;
  }

  _fmtIsoLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  _weekRange() {
    const start = this._today();
    start.setDate(start.getDate() + this._weekOffset * 7);
    const monday = new Date(start);
    const day = monday.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    monday.setDate(monday.getDate() + diff);
    const sunday = new Date(monday);
    sunday.setDate(sunday.getDate() + 6);
    return {
      start: this._fmtIsoLocal(monday),
      end: this._fmtIsoLocal(sunday),
      days: Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday);
        d.setDate(d.getDate() + i);
        return this._fmtIsoLocal(d);
      }),
      monday,
      sunday,
    };
  }

  _fmtDay(iso) {
    const d = new Date(iso + "T12:00:00");
    const wd = d.toLocaleDateString("de-DE", { weekday: "long" });
    const wdShort = d.toLocaleDateString("de-DE", { weekday: "short" }).replace(/\.$/, "");
    const dm = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
    const dayNum = d.getDate();
    const today = this._fmtIsoLocal(this._today());
    return { wd, wdShort, dm, dayNum, today: iso === today };
  }

  _filtered() {
    let list = this._recipes;
    if (this._mealFilter) {
      list = list.filter((r) => (r.tags || []).includes(this._mealFilter));
    }
    if (!this._search) return list;
    const q = this._search.toLowerCase();
    return list.filter((r) =>
      [r.name, r.description, ...(r.tags || []), ...(r.categories || [])]
        .join(" ").toLowerCase().includes(q)
    );
  }

  _recipeMealTags(recipe) {
    return (recipe?.tags || []).filter((t) => MEAL_TAG_IDS.has(t));
  }

  _otherTags(recipe) {
    return (recipe?.tags || []).filter((t) => !MEAL_TAG_IDS.has(t));
  }

  _mealTagLabel(id) {
    return MEALS.find((m) => m.id === id)?.label || id;
  }

  _instructionsToText(steps) {
    return (steps || []).map((s) => String(s).trim()).filter(Boolean).join("\n\n");
  }

  _instructionsFromText(text) {
    return String(text)
      .split(/\n\s*\n/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  _selectedMealTagsFromForm() {
    return MEALS.filter((m) => this.querySelector(`[name="meal-${m.id}"]`)?.checked).map(
      (m) => m.id
    );
  }

  _tagsForSave() {
    const mealTags = this._selectedMealTagsFromForm();
    const other =
      this._mode === "edit" && this._selected ? this._otherTags(this._selected) : [];
    return [...mealTags, ...other];
  }

  _dialogRecipes() {
    const mealType = this._dialog?.type;
    const q = (this._dialogSearch || "").toLowerCase();
    let list = this._recipes;
    if (mealType && !this._dialogShowAll) {
      list = list.filter((r) => (r.tags || []).includes(mealType));
    }
    if (!q) return list;
    return list.filter((r) =>
      [r.name, r.description, ...(r.tags || []), ...(r.categories || [])]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }

  _renderDialogPickList(recipes) {
    if (!recipes.length) {
      return `<p class="muted">Kein passendes Rezept gefunden.</p>`;
    }
    return recipes.map((r) => `
      <button type="button" class="pick-item" data-a="plan-pick" data-id="${r.id}">
        ${this._renderRecipeThumb(r, "xs")}
        <span class="pick-name">${this._esc(r.name)}</span>
      </button>`).join("");
  }

  _plan(date, type) {
    return this._mealplan.find((m) => m.date === date && m.entry_type === type);
  }

  _planName(p) {
    if (!p) return null;
    return p.recipe?.name || p.title || null;
  }

  _planRecipe(p) {
    if (!p) return null;
    if (p.recipe) return p.recipe;
    if (p.recipe_id) {
      return this._recipes.find((r) => r.id === p.recipe_id) || null;
    }
    return null;
  }

  _isWeekend(iso) {
    const day = new Date(iso + "T12:00:00").getDay();
    return day === 0 || day === 6;
  }

  _mealTimeLabel(mealId) {
    const slot = this._mealTimes[mealId];
    if (!slot?.start || !slot?.end) return "";
    return `${this._toTimeInput(slot.start)}–${this._toTimeInput(slot.end)}`;
  }

  _renderPlanCell(day, meal) {
    const { today } = this._fmtDay(day);
    const weekend = this._isWeekend(day);
    const p = this._plan(day, meal.id);
    const name = this._planName(p);
    const recipe = this._planRecipe(p);
    const filled = !!name;
    const cellClass = [
      "plan-cell",
      filled ? "filled" : "empty",
      `meal-${meal.id}`,
      today ? "is-today" : "",
    ].filter(Boolean).join(" ");
    const inner = filled
      ? `
        ${recipe ? `<div class="plan-cell-media">${this._renderRecipeThumb(recipe, "plan")}</div>` : ""}
        <div class="plan-cell-body">
          <span class="plan-name">${this._esc(name)}</span>
        </div>`
      : `
        <span class="plan-empty-icon" aria-hidden="true"><ha-icon icon="mdi:plus-circle-outline"></ha-icon></span>
        <span class="plan-empty">Zuweisen</span>`;
    return `
      <td class="plan-td ${today ? "today-col" : ""} ${weekend ? "weekend-col" : ""}">
        <button type="button" class="${cellClass}" data-a="plan-cell" data-date="${day}" data-type="${meal.id}">
          ${inner}
        </button>
      </td>`;
  }

  _mealLabel(id) {
    return MEALS.find((m) => m.id === id)?.label || id;
  }

  _toTimeInput(value) {
    if (!value) return "";
    const parts = String(value).split(":");
    return `${parts[0].padStart(2, "0")}:${parts[1].padStart(2, "0")}`;
  }

  async _loadMealTimes() {
    if (!this._entryId || !this._hass) return;
    try {
      const res = await this._hass.callWS({
        type: "essensplaner/get_meal_times",
        entry_id: this._entryId,
      });
      this._mealTimes = res || {};
    } catch (e) {
      console.warn("Essensplaner: Essenszeiten laden fehlgeschlagen", e);
    }
  }

  async _saveMealTimes() {
    const meal_times = {};
    for (const m of MEALS) {
      const start = this._formVal(`time-${m.id}-start`);
      const end = this._formVal(`time-${m.id}-end`);
      if (!start || !end) {
        this._notify(`Bitte Zeiten für ${m.label} ausfüllen`, true);
        return;
      }
      if (start >= end) {
        this._notify(`${m.label}: Endzeit muss nach der Startzeit liegen`, true);
        return;
      }
      meal_times[m.id] = { start, end };
    }
    try {
      const res = await this._hass.callWS({
        type: "essensplaner/set_meal_times",
        entry_id: this._entryId,
        meal_times,
      });
      this._mealTimes = res || meal_times;
      this._mealTimesOpen = false;
      this._notify("Essenszeiten gespeichert");
      this._paint();
    } catch (e) {
      const msg = e?.message || String(e);
      this._notify(
        msg.includes("admin") || msg.includes("unauthorized")
          ? "Nur Administratoren können Essenszeiten ändern"
          : "Essenszeiten speichern fehlgeschlagen: " + msg,
        true
      );
    }
  }

  _formVal(field) {
    return this.querySelector(`[name="${field}"]`)?.value ?? "";
  }

  _recipeImage(recipe) {
    const url = recipe?.image_url;
    return url && String(url).trim() ? String(url).trim() : null;
  }

  _renderRecipeThumb(recipe, size = "md") {
    const url = this._recipeImage(recipe);
    if (url) {
      return `<img class="recipe-thumb ${size}" src="${this._esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
    }
    return `<div class="recipe-thumb placeholder ${size}" aria-hidden="true"><ha-icon icon="mdi:food"></ha-icon></div>`;
  }

  _formatIngredient(item) {
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

  _formatServings(servings) {
    if (!servings) return null;
    const text = String(servings).trim();
    const match = text.match(/(\d+)/);
    if (!match) return text;
    const count = parseInt(match[1], 10);
    if (Number.isNaN(count)) return text;
    return count === 1 ? "1 Portion" : `${count} Portionen`;
  }

  _formatDuration(minutes) {
    if (!minutes) return null;
    const mins = Number(minutes);
    if (Number.isNaN(mins) || mins <= 0) return null;
    if (mins < 60) return `${mins} Min.`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h} Std. ${m} Min.` : `${h} Std.`;
  }

  _renderMetaChips(recipe) {
    const chips = [];
    const portions = this._formatServings(recipe.servings);
    if (portions) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:account-group"></ha-icon>${this._esc(portions)}</span>`);
    }
    const prep = this._formatDuration(recipe.prep_time);
    if (prep) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:knife"></ha-icon>${prep}</span>`);
    }
    const cook = this._formatDuration(recipe.cook_time);
    if (cook) {
      chips.push(`<span class="meta-chip"><ha-icon icon="mdi:stove"></ha-icon>${cook}</span>`);
    }
    for (const id of this._recipeMealTags(recipe)) {
      const meal = MEALS.find((m) => m.id === id);
      chips.push(
        `<span class="meta-chip meal-tag"><ha-icon icon="${meal?.icon || "mdi:food"}"></ha-icon>${this._esc(this._mealTagLabel(id))}</span>`
      );
    }
    for (const tag of this._otherTags(recipe).slice(0, 4)) {
      chips.push(`<span class="meta-chip tag">${this._esc(tag)}</span>`);
    }
    return chips.length ? `<div class="meta-chips">${chips.join("")}</div>` : "";
  }

  async _searchRecipesOnline(query) {
    const q = (query || "").trim();
    if (q.length < 2) {
      this._notify("Bitte mindestens 2 Zeichen eingeben", true);
      return [];
    }
    const res = await this._hass.callWS({
      type: "essensplaner/search_recipes_online",
      query: q,
      limit: 12,
    });
    return res?.results || [];
  }

  _renderOnlineThumb(result) {
    if (result?.image_url) {
      return `<img class="recipe-thumb xs" src="${this._esc(result.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
    }
    return this._renderRecipeThumb(null, "xs");
  }

  _renderOnlineResults(results) {
    if (!results?.length) {
      return `<p class="muted">Keine Treffer – anderen Suchbegriff probieren.</p>`;
    }
    return results.map((r) => `
      <div class="online-item">
        <button type="button" class="online-pick" data-a="online-preview" data-url="${this._esc(r.url)}">
          ${this._renderOnlineThumb(r)}
          <div class="online-body">
            <strong>${this._esc(r.title)}</strong>
            <span class="muted">Chefkoch · Vorschau öffnen</span>
          </div>
        </button>
        <button type="button" class="btn primary sm" data-a="online-import" data-url="${this._esc(r.url)}" ${this._onlineImporting ? "disabled" : ""}>
          Importieren
        </button>
      </div>`).join("");
  }

  async _openOnlinePreview(url) {
    const hit = this._inspirationResults.find((r) => r.url === url);
    this._onlinePreview = {
      url,
      title: hit?.title || "",
      image_url: hit?.image_url || "",
      loading: true,
    };
    this._paint();
    try {
      const res = await this._hass.callWS({
        type: "essensplaner/preview_recipe_url",
        url,
      });
      this._onlinePreview = { url, recipe: res?.recipe, loading: false };
    } catch (e) {
      this._onlinePreview = {
        url,
        title: hit?.title || "",
        image_url: hit?.image_url || "",
        loading: false,
        error: e.message || String(e),
      };
    }
    this._paint();
  }

  async _importFromOnline(url) {
    if (!url || this._onlineImporting) return;
    this._onlineImporting = true;
    this._paint();
    try {
      await this._svc("import_recipe", { url }, false);
      await this._load();
      this._onlinePreview = null;
      this._notify("Rezept importiert");
    } catch (e) {
      this._notify("Import fehlgeschlagen: " + (e.message || e), true);
    } finally {
      this._onlineImporting = false;
      this._paint();
    }
  }

  _recipeSummary(recipe) {
    const parts = [];
    const portions = this._formatServings(recipe.servings);
    if (portions) parts.push(portions);
    const prep = this._formatDuration(recipe.prep_time);
    const cook = this._formatDuration(recipe.cook_time);
    if (prep || cook) parts.push([prep, cook].filter(Boolean).join(" + "));
    return parts.join(" · ");
  }

  /* ── actions ──────────────────────────────────────── */

  async _import() {
    const url = this._importUrl.trim();
    if (!url) return;
    this._loading = true;
    this._paint();
    try {
      await this._svc("import_recipe", { url }, false);
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
    const imageUrl = this._formVal("image_url").trim();
    const servings = this._formVal("servings").trim();
    const payload = {
      name,
      description: this._formVal("description").trim(),
      ingredients: this._formVal("ingredients").split("\n").map((s) => s.trim()).filter(Boolean),
      instructions: this._instructionsFromText(this._formVal("instructions")),
      image_url: imageUrl || "",
      servings: servings || "",
      tags: this._tagsForSave(),
    };
    this._loading = true;
    this._paint();
    const editId = this._selected?.id;
    try {
      if (this._mode === "edit" && this._selected) {
        await this._svc("update_recipe", { recipe_id: this._selected.id, ...payload }, true);
        this._notify("Rezept gespeichert");
      } else {
        await this._svc("create_recipe", payload, false);
        this._notify("Rezept erstellt");
      }
      this._formDraft = null;
      this._mode = "view";
      await this._load();
      if (editId) {
        this._selected = this._recipes.find((r) => r.id === editId) || null;
      } else {
        this._selected = null;
      }
    } catch (e) {
      this._loading = false;
      this._notify("Speichern fehlgeschlagen: " + (e.message || e), true);
      this._paint();
    }
  }

  async _deleteRecipe(id) {
    if (!confirm("Rezept wirklich löschen?")) return;
    try {
      await this._svc("delete_recipe", { recipe_id: id }, false);
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
      }, false);
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
      }, false);
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
    if (el.name && (this._mode === "create" || this._mode === "edit")) {
      if (!this._formDraft) this._formDraft = {};
      this._formDraft[el.name] = el.value;
      return;
    }
    if (el.id === "search") {
      this._search = el.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => this._paint(), 200);
      return;
    }
    if (el.id === "dialog-search") {
      this._dialogSearch = el.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => this._paintDialogSearch(), 150);
      return;
    }
    if (el.id === "inspiration-query") {
      this._inspirationQuery = el.value;
      return;
    }
  }

  _paintDialogSearch() {
    if (!this._dialog) return;
    const list = this.querySelector(".pick-list");
    if (!list) return;
    list.innerHTML = this._renderDialogPickList(this._dialogRecipes());
  }

  async _handleChange(ev) {
    if (ev.target.id === "entry-select") {
      this._entryId = ev.target.value;
      this._selected = null;
      this._mode = "view";
      this._mealTimesOpen = false;
      this._dataLoaded = false;
      await this._load();
    }
  }

  async _handleClick(ev) {
    const t = this._clickTarget(ev);
    if (!t) {
      const hitOverlay = ev.composedPath().some(
        (el) => el instanceof HTMLElement && el.classList?.contains("overlay")
      );
      if (hitOverlay && (this._dialog || this._onlinePreview || this._isRecipeModalOpen())) {
        const onBackdrop = ev.composedPath().some(
          (el) => el instanceof HTMLElement && el.classList?.contains("overlay") && el === ev.target
        );
        if (onBackdrop) {
          this._dialog = null;
          this._onlinePreview = null;
          if (this._mode === "edit" && this._selected) {
            this._formDraft = null;
            this._mode = "view";
          } else {
            this._closeRecipeModal();
          }
          this._paint();
        }
      }
      return;
    }
    const a = t.dataset.a;

    if (a === "tab") { this._tab = t.dataset.tab; this._paint(); return; }
    if (a === "reload") { await this._load(); return; }
    if (a === "import") { await this._import(); return; }
    if (a === "new") {
      this._selected = null;
      this._formDraft = null;
      this._mode = "create";
      this._paint();
      return;
    }
    if (a === "filter-meal") {
      this._mealFilter = t.dataset.meal || null;
      this._paint();
      return;
    }
    if (a === "select") {
      this._selected = this._recipes.find((r) => r.id === t.dataset.id) || null;
      this._mode = "view";
      this._paint();
      return;
    }
    if (a === "edit") { this._formDraft = null; this._mode = "edit"; this._paint(); return; }
    if (a === "cancel") {
      this._formDraft = null;
      if (this._mode === "edit" && this._selected) {
        this._mode = "view";
      } else {
        this._closeRecipeModal();
      }
      this._paint();
      return;
    }
    if (a === "recipe-close") {
      if (this._mode === "edit" && this._selected) {
        this._formDraft = null;
        this._mode = "view";
      } else {
        this._closeRecipeModal();
      }
      this._paint();
      return;
    }
    if (a === "save") { await this._saveRecipe(); return; }
    if (a === "delete") { await this._deleteRecipe(t.dataset.id); return; }
    if (a === "shop") { await this._addShopping(t.dataset.id); return; }
    if (a === "week-prev") { this._weekOffset--; await this._reloadPlan(); return; }
    if (a === "week-next") { this._weekOffset++; await this._reloadPlan(); return; }
    if (a === "week-today") { this._weekOffset = 0; await this._reloadPlan(); return; }
    if (a === "times-toggle") {
      this._mealTimesOpen = !this._mealTimesOpen;
      this._paint();
      return;
    }
    if (a === "times-save") { await this._saveMealTimes(); return; }
    if (a === "plan-cell") {
      this._dialog = { date: t.dataset.date, type: t.dataset.type, label: this._mealLabel(t.dataset.type) };
      this._dialogSearch = "";
      this._dialogShowAll = false;
      this._paint();
      return;
    }
    if (a === "dialog-show-all") {
      this._dialogShowAll = !this._dialogShowAll;
      this._paint();
      return;
    }
    if (a === "inspiration-toggle") {
      this._inspirationOpen = !this._inspirationOpen;
      this._paint();
      return;
    }
    if (a === "inspiration-search") {
      this._inspirationLoading = true;
      this._paint();
      try {
        this._inspirationResults = await this._searchRecipesOnline(this._inspirationQuery);
      } catch (e) {
        this._notify("Suche fehlgeschlagen: " + (e.message || e), true);
      } finally {
        this._inspirationLoading = false;
        this._paint();
      }
      return;
    }
    if (a === "online-preview") {
      await this._openOnlinePreview(t.dataset.url);
      return;
    }
    if (a === "online-preview-close") {
      this._onlinePreview = null;
      this._paint();
      return;
    }
    if (a === "online-import") {
      await this._importFromOnline(t.dataset.url);
      return;
    }
    if (a === "plan-pick") { await this._assignPlan(t.dataset.id); return; }
    if (a === "plan-clear") { await this._clearPlan(); return; }
    if (a === "dialog-close") { this._dialog = null; this._paint(); return; }
  }

  /* ── render blocks ────────────────────────────────── */

  _renderForm(r) {
    const base = r || { name: "", description: "", ingredients: [], instructions: [], image_url: "", servings: "", tags: [] };
    let instructionsText = this._instructionsToText(base.instructions);
    let ingredientsText = (base.ingredients || []).map((i) => this._formatIngredient(i)).join("\n");
    const data = {
      name: base.name || "",
      description: base.description || "",
      image_url: base.image_url || "",
      servings: this._formatServings(base.servings) || base.servings || "",
      mealTags: this._recipeMealTags(base),
    };
    if (this._formDraft) {
      if (this._formDraft.name !== undefined) data.name = this._formDraft.name;
      if (this._formDraft.description !== undefined) data.description = this._formDraft.description;
      if (this._formDraft.ingredients !== undefined) ingredientsText = this._formDraft.ingredients;
      if (this._formDraft.instructions !== undefined) instructionsText = this._formDraft.instructions;
      if (this._formDraft.image_url !== undefined) data.image_url = this._formDraft.image_url;
      if (this._formDraft.servings !== undefined) data.servings = this._formDraft.servings;
    }
    const previewUrl = data.image_url?.trim();
    const mealChecks = MEALS.map(
      (m) => `
        <label class="meal-check">
          <input type="checkbox" name="meal-${m.id}" ${data.mealTags.includes(m.id) ? "checked" : ""}>
          <ha-icon icon="${m.icon}"></ha-icon>
          <span>${m.label}</span>
        </label>`
    ).join("");
    return `
      <div class="form-inner">
        <div class="form-preview">
          ${previewUrl
            ? `<img class="form-preview-img" src="${this._esc(previewUrl)}" alt="" referrerpolicy="no-referrer">`
            : `<div class="form-preview-placeholder"><ha-icon icon="mdi:image-plus"></ha-icon><span>Bild-Vorschau</span></div>`}
        </div>
        <label>Name<input class="inp" name="name" value="${this._esc(data.name)}" autofocus></label>
        <label>Portionen <span class="hint">(z. B. 4 oder „4 Portionen“)</span>
          <input class="inp" name="servings" placeholder="4" value="${this._esc(data.servings || "")}"></label>
        <label>Bild-URL <span class="hint">(wird beim Import oft automatisch gesetzt)</span>
          <input class="inp" name="image_url" type="url" placeholder="https://…" value="${this._esc(data.image_url || "")}"></label>
        <fieldset class="meal-tag-field">
          <legend>Mahlzeit</legend>
          <div class="meal-checks">${mealChecks}</div>
        </fieldset>
        <label>Beschreibung<textarea class="inp" name="description" rows="2">${this._esc(data.description || "")}</textarea></label>
        <label>Zutaten <span class="hint">(eine pro Zeile, z. B. „500 g Mehl“ oder „1 EL Öl“)</span>
          <textarea class="inp" name="ingredients" rows="6">${this._esc(ingredientsText)}</textarea></label>
        <label>Zubereitung <span class="hint">(Schritte durch eine Leerzeile trennen; Zeilenumbrüche innerhalb eines Schritts bleiben erhalten)</span>
          <textarea class="inp" name="instructions" rows="8">${this._esc(instructionsText)}</textarea></label>
        <div class="btn-row form-actions">
          <button type="button" class="btn primary" data-a="save">Speichern</button>
          <button type="button" class="btn" data-a="cancel">Abbrechen</button>
        </div>
      </div>`;
  }

  _renderRecipeDetailContent(r) {
    const ings = (r.ingredients || [])
      .map((i) => `<li>${this._esc(this._formatIngredient(i))}</li>`)
      .join("");
    const steps = (r.instructions || [])
      .map((s, idx) => `<li><span class="step-num">${idx + 1}</span><span class="step-text">${this._esc(s)}</span></li>`)
      .join("");
    const source = r.source_url
      ? `<a class="source-link" href="${this._esc(r.source_url)}" target="_blank" rel="noopener">Originalrezept öffnen</a>`
      : "";
    return `
      <article class="detail-card">
        <div class="detail-hero">
          ${this._renderRecipeThumb(r, "hero")}
        </div>
        <div class="detail-body">
          <header class="detail-header">
            <h2>${this._esc(r.name)}</h2>
            ${this._renderMetaChips(r)}
          </header>
          ${r.description ? `<p class="desc">${this._esc(r.description)}</p>` : ""}
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
          <div class="btn-row detail-actions">
            <button type="button" class="btn" data-a="edit"><ha-icon icon="mdi:pencil"></ha-icon> Bearbeiten</button>
            <button type="button" class="btn" data-a="shop" data-id="${r.id}"><ha-icon icon="mdi:cart-plus"></ha-icon> Einkaufsliste</button>
            <button type="button" class="btn danger" data-a="delete" data-id="${r.id}"><ha-icon icon="mdi:delete"></ha-icon> Löschen</button>
          </div>
        </div>
      </article>`;
  }

  _renderRecipeTile(r) {
    const summary = this._recipeSummary(r);
    const mealTags = this._recipeMealTags(r);
    const mealHtml = mealTags.length
      ? `<span class="tile-meals">${mealTags
          .map((id) => `<span class="rc-meal-tag">${this._esc(this._mealTagLabel(id))}</span>`)
          .join("")}</span>`
      : "";
    return `
      <button type="button" class="recipe-tile ${this._selected?.id === r.id ? "on" : ""}" data-a="select" data-id="${r.id}">
        <div class="tile-media">${this._renderRecipeThumb(r, "tile")}</div>
        <div class="tile-body">
          <strong class="tile-title">${this._esc(r.name)}</strong>
          ${mealHtml}
          ${summary ? `<span class="tile-meta">${this._esc(summary)}</span>` : ""}
        </div>
      </button>`;
  }

  _renderRecipeFormModal() {
    const title = this._mode === "edit" ? "Rezept bearbeiten" : "Neues Rezept";
    return `
      <div class="overlay">
        <div class="dialog dialog-recipe-form">
          <div class="dialog-head">
            <h3>${title}</h3>
            <button type="button" class="btn icon close" data-a="recipe-close" title="Schließen">✕</button>
          </div>
          <div class="dialog-scroll">${this._renderForm(this._mode === "edit" ? this._selected : null)}</div>
        </div>
      </div>`;
  }

  _renderRecipeDetailModal() {
    const r = this._selected;
    if (!r) return "";
    return `
      <div class="overlay">
        <div class="dialog dialog-preview dialog-recipe-view">
          <div class="dialog-head">
            <h3>${this._esc(r.name)}</h3>
            <button type="button" class="btn icon close" data-a="recipe-close" title="Schließen">✕</button>
          </div>
          <div class="dialog-scroll">${this._renderRecipeDetailContent(r)}</div>
        </div>
      </div>`;
  }

  _renderRecipeModal() {
    if (this._mode === "create" || this._mode === "edit") {
      return this._renderRecipeFormModal();
    }
    if (this._mode === "view" && this._selected) {
      return this._renderRecipeDetailModal();
    }
    return "";
  }

  _renderRecipesTab() {
    const list = this._filtered();
    const grid = list.length
      ? `<div class="recipe-grid">${list.map((r) => this._renderRecipeTile(r)).join("")}</div>`
      : `<p class="muted center empty-grid">Noch keine Rezepte – URL importieren oder „Neues Rezept“.</p>`;

    return `
      <div class="import-bar">
        <input class="inp grow" id="import-url" placeholder="Rezept-URL einfügen (z. B. Chefkoch)…" value="${this._esc(this._importUrl)}">
        <button class="btn primary" data-a="import">Importieren</button>
        <button class="btn" data-a="new"><ha-icon icon="mdi:plus"></ha-icon> Neues Rezept</button>
      </div>
      <div class="toolbar">
        <input class="inp" id="search" placeholder="Rezepte suchen…" value="${this._esc(this._search)}">
        <span class="badge">${list.length} Rezepte</span>
      </div>
      <div class="meal-filters">
        <button type="button" class="filter-chip ${!this._mealFilter ? "on" : ""}" data-a="filter-meal" data-meal="">Alle</button>
        ${MEALS.map(
          (m) => `
          <button type="button" class="filter-chip ${this._mealFilter === m.id ? "on" : ""}" data-a="filter-meal" data-meal="${m.id}">
            <ha-icon icon="${m.icon}"></ha-icon>${m.label}
          </button>`
        ).join("")}
      </div>
      ${this._renderInspirationSection()}
      ${grid}`;
  }

  _renderMealTimesSection() {
    const rows = MEALS.map((m) => {
      const slot = this._mealTimes[m.id] || { start: "12:00", end: "13:00" };
      return `
        <div class="times-row">
          <span class="times-label"><ha-icon icon="${m.icon}"></ha-icon> ${m.label}</span>
          <label>von
            <input type="time" class="inp time-inp" name="time-${m.id}-start" value="${this._toTimeInput(slot.start)}">
          </label>
          <label>bis
            <input type="time" class="inp time-inp" name="time-${m.id}-end" value="${this._toTimeInput(slot.end)}">
          </label>
        </div>`;
    }).join("");

    return `
      <div class="meal-times-card">
        <button type="button" class="times-toggle" data-a="times-toggle">
          <ha-icon icon="mdi:clock-outline"></ha-icon>
          Essenszeiten
          <ha-icon icon="${this._mealTimesOpen ? "mdi:chevron-up" : "mdi:chevron-down"}"></ha-icon>
        </button>
        ${this._mealTimesOpen ? `
          <p class="muted times-hint">Standard-Uhrzeiten für die Kalenderansicht in Home Assistant.</p>
          <div class="times-grid">${rows}</div>
          <div class="btn-row">
            <button type="button" class="btn primary" data-a="times-save">Speichern</button>
          </div>` : ""}
      </div>`;
  }

  _renderInspirationSection() {
    return `
      <div class="inspiration-card">
        <button type="button" class="times-toggle" data-a="inspiration-toggle">
          <ha-icon icon="mdi:lightbulb-on-outline"></ha-icon>
          Rezept-Inspiration
          <ha-icon icon="${this._inspirationOpen ? "mdi:chevron-up" : "mdi:chevron-down"}"></ha-icon>
        </button>
        ${this._inspirationOpen ? `
          <p class="muted times-hint">Online auf Chefkoch suchen. Rezept anklicken für Vorschau oder direkt importieren.</p>
          <div class="inspiration-search">
            <input class="inp grow" id="inspiration-query" placeholder="z. B. schnelles Abendessen, Linsensuppe, vegetarisch…" value="${this._esc(this._inspirationQuery)}">
            <button type="button" class="btn primary" data-a="inspiration-search" ${this._inspirationLoading ? "disabled" : ""}>Suchen</button>
          </div>
          ${this._inspirationLoading ? `<div class="loading compact"><ha-circular-progress active></ha-circular-progress></div>` : ""}
          <div class="online-list">${this._renderOnlineResults(this._inspirationResults)}</div>` : ""}
      </div>`;
  }

  _renderPlanTab() {
    const { days, monday, sunday } = this._weekRange();
    const weekLabel = `${monday.toLocaleDateString("de-DE", { day: "2-digit", month: "short" })} – ${sunday.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" })}`;

    const head = days.map((day) => {
      const { wdShort, dayNum, today } = this._fmtDay(day);
      const weekend = this._isWeekend(day);
      return `
        <th class="day-head ${today ? "today-col-head" : ""} ${weekend ? "weekend-col-head" : ""}">
          <span class="day-wd">${wdShort}</span>
          <span class="day-num">${dayNum}</span>
          ${today ? `<span class="day-today-badge">Heute</span>` : ""}
        </th>`;
    }).join("");
    const rows = MEALS.map((m) => {
      const timeHint = this._mealTimeLabel(m.id);
      const cells = days.map((day) => this._renderPlanCell(day, m)).join("");
      return `
        <tr class="meal-row meal-row-${m.id}">
          <td class="meal-label meal-row-${m.id}">
            <div class="meal-label-inner">
              <span class="meal-icon-wrap"><ha-icon icon="${m.icon}"></ha-icon></span>
              <span class="meal-label-text">${m.label}</span>
              ${timeHint ? `<span class="meal-time-hint">${timeHint}</span>` : ""}
            </div>
          </td>
          ${cells}
        </tr>`;
    }).join("");

    const onCurrentWeek = this._weekOffset === 0;
    return `
      ${this._renderMealTimesSection()}
      <div class="plan-header-card">
        <div class="week-nav">
          <button type="button" class="btn icon week-btn" data-a="week-prev" title="Vorherige Woche">
            <ha-icon icon="mdi:chevron-left"></ha-icon>
          </button>
          <div class="week-label-wrap">
            <span class="week-kicker">Essensplan</span>
            <span class="week-label">${weekLabel}</span>
          </div>
          <button type="button" class="btn icon week-btn" data-a="week-next" title="Nächste Woche">
            <ha-icon icon="mdi:chevron-right"></ha-icon>
          </button>
          <button type="button" class="btn week-today-btn ${onCurrentWeek ? "muted-btn" : "primary"}" data-a="week-today" ${onCurrentWeek ? "disabled" : ""}>Heute</button>
        </div>
      </div>
      <div class="plan-wrap">
        <table class="plan-grid">
          <thead>
            <tr>
              <th class="corner">
                <span class="corner-label"><ha-icon icon="mdi:silverware-variant"></ha-icon></span>
              </th>
              ${head}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  _renderDialog() {
    if (!this._dialog) return "";
    const { date, type, label } = this._dialog;
    const { wd, dm } = this._fmtDay(date);
    const current = this._planName(this._plan(date, type));
    const picks = this._dialogRecipes();
    const list = this._renderDialogPickList(picks);
    const filterHint = !this._dialogShowAll
      ? `<p class="muted dialog-hint">Zeigt Rezepte mit Tag <strong>${this._esc(label)}</strong>.</p>`
      : `<p class="muted dialog-hint">Alle Rezepte werden angezeigt.</p>`;
    const filterToggle = `<button type="button" class="btn linkish" data-a="dialog-show-all">${this._dialogShowAll ? "Nur passende Tags" : "Alle Rezepte zeigen"}</button>`;

    return `
      <div class="overlay">
        <div class="dialog dialog-wide">
          <div class="dialog-head">
            <h3>${label}</h3>
            <span class="muted">${wd}, ${dm}</span>
            <button type="button" class="btn icon close" data-a="dialog-close" title="Schließen">✕</button>
          </div>
          ${current ? `<div class="current-plan">Aktuell: <strong>${this._esc(current)}</strong></div>` : ""}
          ${filterHint}
          <div class="dialog-filter-row">
            <input class="inp" id="dialog-search" placeholder="In Vorschlägen suchen…" value="${this._esc(this._dialogSearch)}">
            ${filterToggle}
          </div>
          <div class="pick-list">${list}</div>
          <div class="btn-row">
            ${current ? `<button type="button" class="btn danger" data-a="plan-clear">Entfernen</button>` : ""}
            <button type="button" class="btn" data-a="dialog-close">Abbrechen</button>
          </div>
        </div>
      </div>`;
  }

  _renderOnlinePreview() {
    if (!this._onlinePreview) return "";
    const { url, recipe, loading, error, title, image_url } = this._onlinePreview;
    if (loading) {
      const thumb = image_url
        ? `<img class="recipe-thumb hero" src="${this._esc(image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : this._renderRecipeThumb(null, "hero");
      return `
        <div class="overlay">
          <div class="dialog dialog-preview">
            <div class="dialog-head">
              <h3>${this._esc(title || "Rezept-Vorschau")}</h3>
              <button type="button" class="btn icon close" data-a="online-preview-close" title="Schließen">✕</button>
            </div>
            <div class="preview-loading">
              ${thumb}
              <div class="loading compact"><ha-circular-progress active></ha-circular-progress></div>
              <p class="muted">Rezept wird geladen…</p>
            </div>
          </div>
        </div>`;
    }
    if (error || !recipe) {
      return `
        <div class="overlay">
          <div class="dialog dialog-preview">
            <div class="dialog-head">
              <h3>${this._esc(title || "Rezept-Vorschau")}</h3>
              <button type="button" class="btn icon close" data-a="online-preview-close" title="Schließen">✕</button>
            </div>
            <p class="alert">Vorschau fehlgeschlagen: ${this._esc(error || "Unbekannter Fehler")}</p>
            <div class="btn-row">
              <a class="btn" href="${this._esc(url)}" target="_blank" rel="noopener">Auf Chefkoch öffnen</a>
              <button type="button" class="btn" data-a="online-preview-close">Schließen</button>
            </div>
          </div>
        </div>`;
    }
    const ings = (recipe.ingredients || [])
      .map((i) => `<li>${this._esc(this._formatIngredient(i))}</li>`)
      .join("");
    const steps = (recipe.instructions || [])
      .map((s, idx) => `<li><span class="step-num">${idx + 1}</span><span class="step-text">${this._esc(s)}</span></li>`)
      .join("");
    const source = recipe.source_url || url;
    return `
      <div class="overlay">
        <div class="dialog dialog-preview">
          <div class="dialog-head">
            <h3>${this._esc(recipe.name)}</h3>
            <button type="button" class="btn icon close" data-a="online-preview-close" title="Schließen">✕</button>
          </div>
          <article class="preview-card">
            <div class="detail-hero">${this._renderRecipeThumb(recipe, "hero")}</div>
            <div class="detail-body">
              ${this._renderMetaChips(recipe)}
              ${recipe.description ? `<p class="desc">${this._esc(recipe.description)}</p>` : ""}
              <a class="source-link" href="${this._esc(source)}" target="_blank" rel="noopener">Originalrezept auf Chefkoch</a>
              <div class="detail-sections preview-sections">
                <section class="detail-panel">
                  <h4><ha-icon icon="mdi:basket"></ha-icon> Zutaten</h4>
                  <ul class="ingredient-list">${ings || "<li class='muted'>Keine Zutaten</li>"}</ul>
                </section>
                <section class="detail-panel">
                  <h4><ha-icon icon="mdi:pot-steam"></ha-icon> Zubereitung</h4>
                  <ol class="step-list">${steps || "<li class='muted'>Keine Schritte</li>"}</ol>
                </section>
              </div>
            </div>
          </article>
          <div class="btn-row">
            <button type="button" class="btn primary" data-a="online-import" data-url="${this._esc(url)}" ${this._onlineImporting ? "disabled" : ""}>In Sammlung importieren</button>
            <button type="button" class="btn" data-a="online-preview-close">Schließen</button>
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
      ${this._renderDialog()}
      ${this._renderOnlinePreview()}
      ${this._renderRecipeModal()}`;
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
  .content { padding: 20px 24px 40px; max-width: 1680px; margin: 0 auto; }
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
  .recipe-grid {
    display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px;
  }
  @media (max-width: 1400px) { .recipe-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
  @media (max-width: 1100px) { .recipe-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
  @media (max-width: 760px) { .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 440px) { .recipe-grid { grid-template-columns: 1fr; } }
  .empty-grid { grid-column: 1 / -1; padding: 32px 0; }
  .recipe-tile {
    display: flex; flex-direction: column; width: 100%; text-align: left;
    padding: 0; border-radius: 12px; cursor: pointer; overflow: hidden;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #e8e8e8);
    transition: border-color .15s, box-shadow .15s, transform .12s;
    font: inherit; color: inherit;
  }
  .recipe-tile:hover { border-color: var(--primary-color); box-shadow: 0 6px 18px rgba(0,0,0,.08); transform: translateY(-2px); }
  .recipe-tile.on { border-color: var(--primary-color); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 25%, transparent); }
  .tile-media {
    aspect-ratio: 4 / 3; overflow: hidden; background: var(--secondary-background-color, #eee);
  }
  .tile-media .recipe-thumb { width: 100%; height: 100%; border-radius: 0; object-fit: cover; }
  .tile-media .recipe-thumb.placeholder { width: 100%; height: 100%; border-radius: 0; }
  .tile-body { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px 12px; min-width: 0; }
  .tile-title {
    font-size: 0.9rem; line-height: 1.35; font-weight: 600;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .tile-meals { display: flex; flex-wrap: wrap; gap: 4px; }
  .tile-meta { font-size: 0.75rem; color: var(--primary-color); font-weight: 500; }
  .recipe-thumb {
    object-fit: cover; border-radius: 10px; flex-shrink: 0; background: var(--secondary-background-color, #f0f0f0);
  }
  .recipe-thumb.sm { width: 72px; height: 72px; }
  .recipe-thumb.tile { width: 100%; height: 100%; border-radius: 0; }
  .recipe-thumb.plan { width: 100%; height: 100%; border-radius: 0; object-fit: cover; }
  .recipe-thumb.xs { width: 44px; height: 44px; border-radius: 8px; }
  .recipe-thumb.hero { width: 100%; height: 100%; border-radius: 0; min-height: 220px; max-height: 320px; }
  .recipe-thumb.placeholder {
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, color-mix(in srgb, var(--primary-color) 16%, #f5f5f5), var(--secondary-background-color, #eee));
    color: var(--primary-color);
  }
  .recipe-thumb.placeholder ha-icon { --mdc-icon-size: 28px; opacity: .7; }
  .recipe-thumb.placeholder.hero ha-icon { --mdc-icon-size: 56px; }
  .recipe-thumb.placeholder.sm ha-icon { --mdc-icon-size: 24px; }
  .detail-card, .form-inner {
    background: var(--card-background-color, #fff);
    border-radius: 14px; overflow: hidden;
    border: 1px solid var(--divider-color, #e8e8e8);
    box-shadow: 0 2px 12px rgba(0,0,0,.05);
  }
  .detail-hero { aspect-ratio: 16 / 9; max-height: 320px; overflow: hidden; background: var(--secondary-background-color, #eee); }
  .detail-body { padding: 20px 24px 24px; }
  .detail-header { margin-bottom: 12px; }
  .detail-header h2 { margin: 0 0 10px; font-size: 1.5rem; line-height: 1.25; }
  .meta-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .meta-chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 5px 10px; border-radius: 999px; font-size: 0.8rem;
    background: var(--secondary-background-color, #f5f5f5); color: var(--secondary-text-color);
  }
  .meta-chip ha-icon { --mdc-icon-size: 16px; }
  .meta-chip.tag { background: color-mix(in srgb, var(--primary-color) 12%, transparent); color: var(--primary-color); }
  .meta-chip.meal-tag { background: color-mix(in srgb, var(--primary-color) 14%, transparent); color: var(--primary-color); font-weight: 500; }
  .meal-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  .filter-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border-radius: 999px; border: 1px solid var(--divider-color, #ddd);
    background: var(--card-background-color, #fff); cursor: pointer; font: inherit; font-size: 0.85rem;
    color: var(--secondary-text-color); transition: border-color .12s, background .12s;
  }
  .filter-chip ha-icon { --mdc-icon-size: 16px; }
  .filter-chip.on {
    border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    color: var(--primary-color); font-weight: 500;
  }
  .filter-chip:hover:not(.on) { border-color: var(--primary-color); }
  .rc-meals { display: flex; flex-wrap: wrap; gap: 4px; }
  .rc-meal-tag {
    font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 999px;
    background: color-mix(in srgb, var(--primary-color) 12%, transparent); color: var(--primary-color);
  }
  .meal-tag-field { border: none; margin: 0 0 14px; padding: 0; }
  .meal-tag-field legend { font-size: 0.9rem; font-weight: 500; margin-bottom: 8px; padding: 0; }
  .meal-checks { display: flex; flex-wrap: wrap; gap: 10px; }
  .meal-check {
    display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px;
    border-radius: 10px; border: 1px solid var(--divider-color, #ddd);
    background: var(--secondary-background-color, #fafafa); cursor: pointer; font-size: 0.88rem;
  }
  .meal-check:has(input:checked) {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color, #fff));
    color: var(--primary-color);
  }
  .meal-check input { margin: 0; }
  .meal-check ha-icon { --mdc-icon-size: 18px; }
  .desc { color: var(--secondary-text-color); line-height: 1.55; margin: 0 0 12px; }
  .source-link { display: inline-block; margin-bottom: 16px; font-size: 0.85rem; color: var(--primary-color); text-decoration: none; }
  .source-link:hover { text-decoration: underline; }
  .detail-sections {
    display: grid; grid-template-columns: 1fr 1.2fr; gap: 16px; margin-top: 8px;
  }
  @media (max-width: 800px) { .detail-sections { grid-template-columns: 1fr; } }
  .detail-panel {
    padding: 16px; border-radius: 12px;
    background: var(--secondary-background-color, #fafafa);
    border: 1px solid var(--divider-color, #eee);
  }
  .detail-panel h4 {
    display: flex; align-items: center; gap: 8px; margin: 0 0 12px;
    font-size: 0.88rem; text-transform: uppercase; letter-spacing: .04em;
    color: var(--secondary-text-color);
  }
  .detail-panel h4 ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
  .ingredient-list, .step-list { margin: 0; padding: 0; list-style: none; line-height: 1.55; }
  .ingredient-list li { padding: 7px 0; border-bottom: 1px solid var(--divider-color, #e8e8e8); font-size: 0.92rem; }
  .ingredient-list li:last-child { border-bottom: none; }
  .step-list li { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--divider-color, #e8e8e8); font-size: 0.92rem; }
  .step-list li:last-child { border-bottom: none; }
  .step-num {
    flex-shrink: 0; width: 26px; height: 26px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    font-size: 0.78rem; font-weight: 600;
  }
  .step-text { flex: 1; padding-top: 3px; white-space: pre-line; }
  .detail-actions { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--divider-color, #e8e8e8); }
  .detail-actions .btn ha-icon { --mdc-icon-size: 18px; }
  .form-inner { padding: 0; }
  .form-preview {
    margin-bottom: 16px; border-radius: 12px; overflow: hidden;
    aspect-ratio: 16 / 9; max-height: 200px; background: var(--secondary-background-color, #f5f5f5);
    border: 1px dashed var(--divider-color, #ccc);
  }
  .form-preview-img { width: 100%; height: 100%; object-fit: cover; }
  .form-preview-placeholder {
    height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; color: var(--secondary-text-color); font-size: 0.85rem;
  }
  .form-preview-placeholder ha-icon { --mdc-icon-size: 36px; opacity: .5; }
  .form-inner label { display: block; margin-bottom: 14px; font-size: 0.9rem; font-weight: 500; }
  .form-inner textarea { resize: vertical; }
  .form-actions { margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--divider-color, #e8e8e8); }
  .hint { font-weight: 400; color: var(--secondary-text-color); font-size: 0.8rem; }
  .meal-times-card, .inspiration-card {
    margin-bottom: 16px; padding: 14px 16px; border-radius: 12px;
    border: 1px solid var(--divider-color, #e8e8e8);
    background: var(--card-background-color, #fff);
  }
  .inspiration-search { display: flex; gap: 10px; margin: 12px 0; flex-wrap: wrap; }
  .online-list { display: flex; flex-direction: column; gap: 8px; max-height: 42vh; overflow-y: auto; }
  .dialog-online { max-height: 36vh; }
  .online-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border: 1px solid var(--divider-color, #eee); border-radius: 10px;
    background: var(--secondary-background-color, #fafafa);
  }
  .online-pick {
    flex: 1; min-width: 0; display: flex; gap: 10px; align-items: center;
    border: none; background: none; cursor: pointer; text-align: left;
    padding: 0; font: inherit; color: inherit;
  }
  .online-pick:hover .online-body strong { color: var(--primary-color); }
  .online-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .online-body strong { font-size: 0.9rem; line-height: 1.3; }
  .dialog-preview { overflow-y: auto; }
  .preview-loading {
    display: flex; flex-direction: column; align-items: center; gap: 12px;
    padding: 12px 0 20px;
  }
  .preview-card .detail-hero { margin-bottom: 12px; }
  .preview-sections {
    margin-top: 16px;
    grid-template-columns: minmax(220px, 1fr) minmax(320px, 1.5fr);
  }
  @media (max-width: 700px) {
    .preview-sections { grid-template-columns: 1fr; }
  }
  .btn.sm { padding: 7px 12px; font-size: 0.82rem; }
  .loading.compact { padding: 16px; text-align: center; }
  .dialog-wide { max-width: 520px; }
  .dialog-tabs { display: flex; gap: 6px; margin-bottom: 12px; }
  .dialog-tab {
    flex: 1; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--divider-color, #ddd);
    background: var(--card-background-color, #fff); cursor: pointer; font: inherit; font-size: 0.88rem;
  }
  .dialog-tab.on { border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 10%, transparent); color: var(--primary-color); font-weight: 500; }
  .dialog-hint { margin: 0 0 8px; font-size: 0.85rem; }
  .dialog-filter-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
  .dialog-filter-row .inp { flex: 1; min-width: 180px; }
  .btn.linkish {
    padding: 0; border: none; background: none; color: var(--primary-color);
    cursor: pointer; font: inherit; font-size: 0.85rem; text-decoration: underline;
    white-space: nowrap;
  }
  .times-toggle {
    display: flex; align-items: center; gap: 8px; width: 100%;
    padding: 0; border: none; background: none; cursor: pointer;
    font: inherit; font-weight: 500; color: inherit;
  }
  .times-toggle ha-icon { --mdc-icon-size: 20px; color: var(--primary-color); }
  .times-toggle ha-icon:last-child { margin-left: auto; color: var(--secondary-text-color); }
  .times-hint { margin: 12px 0 8px; font-size: 0.85rem; }
  .times-grid { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
  .times-row {
    display: grid; grid-template-columns: minmax(120px, 1fr) 1fr 1fr; gap: 10px; align-items: center;
  }
  @media (max-width: 700px) {
    .times-row { grid-template-columns: 1fr; }
  }
  .times-label { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; font-weight: 500; }
  .times-label ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
  .times-row label { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--secondary-text-color); }
  .time-inp { width: auto; min-width: 7rem; padding: 8px 10px; }
  .plan-header-card {
    margin-bottom: 16px; padding: 14px 18px; border-radius: 14px;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #e8e8e8);
    box-shadow: 0 2px 12px rgba(0,0,0,.04);
  }
  .week-nav {
    display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap;
  }
  .week-btn {
    border-radius: 999px; width: 40px; height: 40px;
    display: inline-flex; align-items: center; justify-content: center;
    border-color: var(--divider-color, #ddd);
  }
  .week-label-wrap { display: flex; flex-direction: column; align-items: center; min-width: 200px; gap: 2px; }
  .week-kicker {
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: .08em;
    color: var(--secondary-text-color); font-weight: 600;
  }
  .week-label { font-weight: 600; font-size: 1.1rem; line-height: 1.2; }
  .week-today-btn { margin-left: 4px; border-radius: 999px; }
  .week-today-btn.muted-btn { opacity: .55; cursor: default; }
  .plan-wrap {
    overflow-x: auto; border-radius: 16px;
    border: 1px solid var(--divider-color, #e8e8e8);
    background: var(--card-background-color, #fff);
    box-shadow: 0 4px 24px rgba(0,0,0,.06);
    padding: 12px;
  }
  .plan-grid { width: 100%; border-collapse: separate; border-spacing: 8px; min-width: 720px; }
  .plan-grid th, .plan-grid td { padding: 0; border: none; vertical-align: middle; }
  .plan-grid th.corner {
    width: 108px; min-width: 108px; vertical-align: bottom; padding-bottom: 6px;
  }
  .corner-label {
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 10px;
    background: var(--secondary-background-color, #f5f5f5);
    color: var(--secondary-text-color);
  }
  .corner-label ha-icon { --mdc-icon-size: 20px; }
  .day-head {
    min-width: 96px; text-align: center; padding: 4px 6px 8px;
    vertical-align: bottom;
  }
  .day-wd {
    display: block; font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em;
    color: var(--secondary-text-color); font-weight: 600;
  }
  .day-num {
    display: block; font-size: 1.35rem; font-weight: 700; line-height: 1.1; margin-top: 2px;
  }
  .day-today-badge {
    display: inline-block; margin-top: 6px; padding: 2px 8px; border-radius: 999px;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
  }
  .today-col-head .day-num { color: var(--primary-color); }
  .weekend-col-head .day-wd, .weekend-col-head .day-num { opacity: .72; }
  .meal-label { width: 108px; min-width: 108px; vertical-align: middle; }
  .meal-label-inner {
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    padding: 8px 6px; text-align: center;
  }
  .meal-icon-wrap {
    display: flex; align-items: center; justify-content: center;
    width: 40px; height: 40px; border-radius: 12px;
    background: color-mix(in srgb, var(--primary-color) 12%, var(--card-background-color, #fff));
    color: var(--primary-color);
  }
  .meal-icon-wrap ha-icon { --mdc-icon-size: 22px; }
  .meal-row-breakfast .meal-icon-wrap {
    background: color-mix(in srgb, #e65100 14%, var(--card-background-color, #fff));
    color: #e65100;
  }
  .meal-row-lunch .meal-icon-wrap {
    background: color-mix(in srgb, #2e7d32 14%, var(--card-background-color, #fff));
    color: #2e7d32;
  }
  .meal-row-dinner .meal-icon-wrap {
    background: color-mix(in srgb, #5e35b1 14%, var(--card-background-color, #fff));
    color: #5e35b1;
  }
  .meal-label-text { font-size: 0.82rem; font-weight: 600; line-height: 1.25; }
  .meal-time-hint { font-size: 0.72rem; color: var(--secondary-text-color); white-space: nowrap; }
  .plan-td { vertical-align: stretch; }
  .weekend-col .plan-cell.empty { background: color-mix(in srgb, var(--secondary-background-color, #f5f5f5) 80%, transparent); }
  .plan-cell {
    width: 100%; min-height: 104px; padding: 0; margin: 0;
    border-radius: 14px; cursor: pointer; text-align: center; font: inherit; color: inherit;
    display: flex; flex-direction: column; align-items: stretch; justify-content: center;
    transition: transform .14s, box-shadow .14s, border-color .14s, background .14s;
    overflow: hidden;
  }
  .plan-cell.empty {
    gap: 6px; padding: 14px 10px;
    border: 2px dashed color-mix(in srgb, var(--divider-color, #ccc) 90%, transparent);
    background: color-mix(in srgb, var(--secondary-background-color, #fafafa) 70%, var(--card-background-color, #fff));
  }
  .plan-cell.empty:hover {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 6%, var(--card-background-color, #fff));
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(0,0,0,.06);
  }
  .plan-cell.filled {
    border: 1px solid color-mix(in srgb, var(--primary-color) 22%, var(--divider-color, #ddd));
    background: var(--card-background-color, #fff);
    box-shadow: 0 2px 10px rgba(0,0,0,.04);
  }
  .plan-cell.filled:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(0,0,0,.1);
    border-color: var(--primary-color);
  }
  .plan-cell.is-today.filled {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 35%, transparent), 0 4px 16px rgba(0,0,0,.06);
  }
  .plan-cell.meal-breakfast.filled { border-color: color-mix(in srgb, #e65100 35%, var(--divider-color, #ddd)); }
  .plan-cell.meal-lunch.filled { border-color: color-mix(in srgb, #2e7d32 35%, var(--divider-color, #ddd)); }
  .plan-cell.meal-dinner.filled { border-color: color-mix(in srgb, #5e35b1 35%, var(--divider-color, #ddd)); }
  .plan-cell-media {
    height: 58px; overflow: hidden; flex-shrink: 0;
    background: var(--secondary-background-color, #eee);
  }
  .plan-cell-media .recipe-thumb.placeholder { width: 100%; height: 100%; border-radius: 0; }
  .plan-cell-media .recipe-thumb.placeholder ha-icon { --mdc-icon-size: 22px; }
  .plan-cell-body { padding: 10px 10px 12px; text-align: left; flex: 1; display: flex; align-items: flex-start; }
  .plan-name {
    font-size: 0.84rem; font-weight: 600; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .plan-empty-icon { color: var(--secondary-text-color); opacity: .65; }
  .plan-empty-icon ha-icon { --mdc-icon-size: 26px; }
  .plan-empty { font-size: 0.78rem; font-weight: 500; color: var(--secondary-text-color); }
  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.45);
    display: flex; align-items: center; justify-content: center;
    z-index: 300; padding: 16px;
  }
  .dialog {
    background: var(--card-background-color, #fff);
    border-radius: 14px; width: 100%; max-width: 420px;
    max-height: 80vh; display: flex; flex-direction: column;
    box-shadow: 0 12px 40px rgba(0,0,0,.2); padding: 20px;
  }
  .dialog.dialog-preview {
    max-width: min(1080px, 96vw);
    max-height: 92vh;
    padding: 24px 28px;
  }
  .dialog.dialog-recipe-form {
    max-width: min(720px, 96vw);
    max-height: 92vh;
  }
  .dialog-recipe-view .detail-card { border: none; box-shadow: none; }
  .dialog-scroll {
    overflow-y: auto; flex: 1; min-height: 0;
    margin: 0 -4px; padding: 0 4px;
  }
  .dialog-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; }
  .dialog-head h3 { margin: 0; flex: 1; }
  .dialog-head .close { margin-left: auto; }
  .current-plan { padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); margin-bottom: 12px; font-size: 0.9rem; }
  .pick-list { overflow-y: auto; flex: 1; margin: 12px 0; display: flex; flex-direction: column; gap: 4px; max-height: 40vh; }
  .pick-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border: 1px solid var(--divider-color, #eee); border-radius: 8px;
    background: var(--card-background-color, #fff); cursor: pointer;
    font: inherit; text-align: left; width: 100%;
  }
  .pick-item:hover { border-color: var(--primary-color); background: var(--secondary-background-color); }
  .pick-name { flex: 1; min-width: 0; text-align: left; }
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
