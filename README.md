# Skills & Plugin Hub (`skills-manager`) for Antigravity

A visual sidecar and interactive dashboard to manage, inspect, search, and enable/disable Antigravity skills and plugins.

---

## Features

- **Sidecar Web UI**: Runs inside Antigravity's Aux Pane (`SIDECAR_UI_ENTRYPOINT_AUX_PANE`) or opens in any local browser at `http://127.0.0.1:18767/`.
- **Live Plugin Toggles**: Toggle any plugin Enabled/Disabled on the fly with atomic synchronization to `~/.gemini/config/config.json`.
- **Host Protection Safeguard**: `skills-manager` itself cannot be disabled from within the UI or via bulk disable, preventing accidental lockout.
- **Accurate Trigger Classification**: Distinguishes between `Slash Command` triggers (e.g. `/pentest`, `/superpowers`, `/documents`), `Hybrid` triggers, and `Auto-Activated` background skills (e.g. `chrome-extensions`, `gemini-api-dev`).
- **Multi-Command Visibility**: Displays all registered slash commands (e.g. `/skills` and `/skills-manager`) with one-click copy to prompt.
- **Deep Reference Guide Reader**: Modal viewer with breadcrumb back-navigation, table rendering, grouped lists, code highlighting, and interactive document linking.
- **Script & Automation Inspector**: Inspect and view bundled helper scripts (e.g. `get_usage.ps1`) right inside the UI.
- **Sidecar Integrations**: Displays background sidecars with views and direct access to `sidecar.json`.
- **Instant Search & Filter**: Real-time filtering by capability, keyword, plugin status (`All`, `Enabled`, `Disabled`, `Custom`, `Official`, `Commands`, `Auto-Activated`).

---

## Directory Structure

```text
skills-manager/
├── plugin.json                              # Plugin definition and metadata
├── README.md                                # Documentation
├── assets/
│   └── logo.svg                             # Hub icon
├── sidecars/
│   └── skills-manager/
│       ├── sidecar.json                     # Antigravity sidecar configuration
│       └── server.py                        # Python ThreadingHTTPServer & Web UI
├── skills/
│   └── skills-manager/
│       └── SKILL.md                         # Skill definition (/skills, /skills-manager)
└── tests/
    ├── test_server.py                       # Comprehensive test suite (9 test suites)
    ├── test_config_safety.py                # Persistence and safeguard tests
    ├── test_doc_reader.py                   # File reader & traversal security tests
    ├── test_markdown_parser.py              # Markdown parsing and list grouping tests
    └── test_parse_skills.py                 # Skill metadata extraction tests
```

---

## API Endpoints

- `GET /` — Responsive Bento UI for Aux Pane and browser.
- `GET /preload.js` — Sidecar SDK preload script.
- `GET /api/health` — Health check endpoint (`{"status": "healthy", "port": 18767}`).
- `GET /api/plugins` — Scans and returns all installed plugins, skills, guides, scripts, and stats.
- `GET /api/doc?path=<path>&baseDirHint=<dir>` — Reads markdown or script content with path-traversal protection.
- `POST /api/toggle` — Toggles a plugin's state (`{"pluginId": "xxx", "enabled": true/false}`).
- `POST /api/bulk-toggle` — Bulk enables or bulk disables plugins (`{"action": "enable_all" | "disable_all"}`).

---

## Verification

To run the automated regression test suite:

```bash
python tests/test_server.py
```
