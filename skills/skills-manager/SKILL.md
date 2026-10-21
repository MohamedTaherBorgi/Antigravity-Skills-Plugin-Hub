---
name: skills-manager
description: >-
  Inspect, search, and manage all installed Antigravity plugins and custom skills.
  Provides a live visual dashboard, enable/disable plugin toggles, slash command index,
  and quick reference documentation viewer. Trigger on "/skills", "/skills-manager",
  "list my skills", "what skills do I have", or "manage plugins".
---

# Skills & Plugin Hub (`skills-manager`)

The **Skills & Plugin Hub** gives you full visibility and live control over every capability installed in Antigravity. It features an interactive Aux-Pane Web UI dashboard and command-line management for all official and custom agent plugins.

---

## Quick Slash Commands

- `/skills` or `/skills-manager`: View all installed skills, active plugins, and status summary.
- Open the **Skills Hub** sidecar panel in the Aux Pane to access the live visual dashboard.

---

## Features

1. **Visual Bento Dashboard**: Live overview of all installed plugins, active/disabled status, skills count, reference guides, and slash commands.
2. **Live Plugin Toggles**: Toggle any plugin Enabled or Disabled in real-time. Changes are instantly synchronized with `config.json`.
3. **Skill & Guide Inspector**: Built-in modal reader for all deep reference guides (`SKILL.md`, references, and scripts).
4. **Slash Command Catalog**: One-click copying of all available slash triggers (`/pentest`, `/superpowers`, `/ui-design`, `/documents`, `/exam-prep`, `/usage-stats`, etc.).
5. **Instant Filtering**: Real-time search across names, tags, slash commands, and deep technical capabilities.

---

## Management API Endpoints

The sidecar runs a local HTTP server exposing:
- `GET /api/plugins`: Full JSON metadata tree of all plugins and skills.
- `POST /api/toggle`: Toggle plugin state (`{"pluginId": "xxx", "enabled": true/false}`).
- `POST /api/bulk-toggle`: Enable or disable all plugins simultaneously.
- `GET /api/doc`: View markdown content for any skill or reference guide.
- `GET /`: The responsive single-page visual UI.
