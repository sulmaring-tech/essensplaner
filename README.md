# Essensplaner – Home Assistant Integration

![Essensplaner Logo](custom_components/essensplaner/brand/logo.png)

Ein **lokaler Rezeptmanager, Essensplaner und Einkaufslisten-Plugin** für Home Assistant – inspiriert von [Mealie](https://mealie.io), aber ohne separaten Server.

Das Plugin-Logo liegt unter `custom_components/essensplaner/brand/` (`icon.png`, `icon@2x.png`, `logo.png`) und wird von Home Assistant ab 2026.3 in der Integrations-UI angezeigt.

**HACS-Listenansicht:** Zeigt ggf. noch ein Platzhalterbild, weil HACS dort weiterhin die Brands-CDN nutzt. Das Icon im Update-Dialog und unter *Einstellungen → Geräte & Dienste* ist korrekt. Details und CDN-Einreichung: siehe [`brands/README.md`](brands/README.md).

## Funktionen

| Bereich | Funktion |
|---------|----------|
| **Web-Panel** | Sidebar „Essensplaner“ – Rezepte importieren, anlegen, ansehen, Wochenplan |
| **Rezepte** | Manuell erstellen, von URLs importieren, suchen, löschen |
| **Essensplan** | Frühstück, Mittag & Abendessen im Panel + Kalender-Entitäten |
| **Einkaufsliste** | Native To-do-Listen mit Abhaken, Sortieren, Zutaten aus Rezepten |
| **Kochbücher** | Rezeptsammlungen (Datenmodell + Service) |
| **Sensoren** | Anzahl Rezepte, Kategorien, Tags, Werkzeuge, Kochbücher |
| **Automatisierungen** | Services kompatibel mit Mealie-Workflows |

Alle Daten werden lokal in Home Assistant gespeichert (`.storage/essensplaner.*`).

## Installation

### Manuell

1. Kopiere den Ordner `custom_components/essensplaner` nach `config/custom_components/essensplaner`
2. Starte Home Assistant neu
3. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
4. Suche nach **Essensplaner** und gib einen Haushaltsnamen ein

### HACS

1. Repository als benutzerdefiniertes Repository hinzufügen: `https://github.com/sulmaring-tech/essensplaner`
2. Integration installieren und Home Assistant neu starten
3. Updates erscheinen als Versionsnummer (z. B. `v1.0.4`), sobald [GitHub Releases](https://github.com/sulmaring-tech/essensplaner/releases) veröffentlicht sind

## Services

| Service | Beschreibung |
|---------|--------------|
| `essensplaner.import_recipe` | Rezept von URL importieren |
| `essensplaner.create_recipe` | Rezept manuell anlegen |
| `essensplaner.delete_recipe` | Rezept löschen |
| `essensplaner.get_recipe` | Einzelnes Rezept abrufen |
| `essensplaner.get_recipes` | Rezepte suchen |
| `essensplaner.get_mealplan` | Essensplan für Zeitraum |
| `essensplaner.set_mealplan` | Gericht/Notiz planen |
| `essensplaner.set_random_mealplan` | Zufälliges Rezept planen |
| `essensplaner.clear_mealplan` | Geplanten Eintrag entfernen |
| `essensplaner.add_recipe_to_shopping_list` | Zutaten zur Einkaufsliste |
| `essensplaner.update_recipe` | Bestehendes Rezept ändern |
| `essensplaner.get_cookbooks` | Kochbücher inkl. Rezepten auflisten |
| `essensplaner.create_cookbook` | Kochbuch anlegen (nur Service) |
| `essensplaner.delete_cookbook` | Kochbuch löschen |
| `essensplaner.add_recipe_to_cookbook` | Rezept einem Kochbuch zuordnen |
| `essensplaner.remove_recipe_from_cookbook` | Rezept aus Kochbuch entfernen |
| `essensplaner.get_shopping_list_items` | Einkaufsliste (auf To-do-Entität) |

### Beispiel: Rezept importieren

```yaml
action: essensplaner.import_recipe
data:
  config_entry_id: <deine_config_entry_id>
  url: "https://www.chefkoch.de/rezept/..."
```

### Beispiel: Heutiges Abendessen als Sensor

```yaml
template:
  - triggers:
      - trigger: time_pattern
        hours: /1
    actions:
      - action: essensplaner.get_mealplan
        data:
          config_entry_id: <deine_config_entry_id>
        response_variable: result
    sensor:
      - name: "Abendessen heute"
        unique_id: essensplaner_dinner_today
        state: >
          {% for meal in result.mealplan if meal.entry_type == "dinner" -%}
          {{ meal.recipe.name if meal.recipe else meal.title }}
          {%- endfor %}
```

### Beispiel: Zufälliges Abendessen planen

```yaml
action: essensplaner.set_random_mealplan
data:
  config_entry_id: <deine_config_entry_id>
  date: "{{ now().date() }}"
  entry_type: dinner
```

## Entitäten

Nach der Einrichtung werden automatisch erstellt:

- **Kalender**: Frühstück, Mittagessen, Abendessen, Beilage, Dessert, Getränk, Snack
- **To-do**: Einkaufsliste (weitere Listen über Daten/API erweiterbar)
- **Sensoren**: Rezepte, Kategorien, Tags, Werkzeuge, Kochbücher

## Web-Panel (Sidebar)

Nach Installation und **vollständigem Neustart** von Home Assistant erscheint in der Sidebar **Essensplaner** (Icon: 🍽️).

Falls der Eintrag fehlt: **Profil (unten links) → Sidebar anpassen** und „Essensplaner“ aktivieren. Direktaufruf: `http://<deine-ha>:8123/essensplaner`

| Tab | Funktionen |
|-----|------------|
| **Rezepte** | URL importieren, manuell anlegen, suchen, Zutaten & Zubereitung ansehen, bearbeiten, löschen, zur Einkaufsliste |
| **Essensplan** | Wochenübersicht mit Frühstück, Mittag- und Abendessen – Rezept per Klick zuweisen oder entfernen |

Geplante Gerichte erscheinen zusätzlich auf den Kalender-Entitäten und können im Dashboard angezeigt werden.

### Alternativ per Services

Rezepte und Planung lassen sich weiterhin per Automatisierung steuern – siehe [`examples/import_startrezepte.yaml`](examples/import_startrezepte.yaml) und [`examples/dashboard_essensplaner.yaml`](examples/dashboard_essensplaner.yaml).

## Abgrenzung zu Mealie

Essensplaner ist eine **eingebettete Lösung** ohne separaten Mealie-Server. Das Panel deckt Rezepte und Wochenplan ab; Einkauf läuft über native To-do-Listen, Kochbücher derzeit nur per Service.

## Lizenz

MIT
