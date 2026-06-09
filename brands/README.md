# Brand-Assets für HACS-Listenansicht

Home Assistant 2026.3+ lädt Icons für **installierte** Integrationen lokal aus `custom_components/essensplaner/brand/`.

Die **HACS-Listenansicht** nutzt aktuell noch `https://brands.home-assistant.io/_/essensplaner/icon.png`. Ohne Eintrag dort erscheint ein Platzhalter – im Update-Dialog funktioniert das lokale Icon bereits.

## CDN-Eintrag (empfohlen für HACS-Liste)

1. [home-assistant/brands](https://github.com/home-assistant/brands) forken
2. Dateien aus `brands/custom_integrations/essensplaner/` nach `custom_integrations/essensplaner/` kopieren
3. Pull Request erstellen

Hinweis: Neue Custom-Integrationen werden teils automatisch abgelehnt. Der PR ist dennoch der offizielle Weg, bis HACS die lokale Brands-API in der Liste unterstützt ([HACS #5223](https://github.com/hacs/integration/issues/5223)).
