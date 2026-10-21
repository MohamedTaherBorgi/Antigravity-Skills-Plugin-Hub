#!/usr/bin/env python3
"""
Skills & Plugin Hub - Antigravity Sidecar Server
Provides visual dashboard, metadata inspection, live plugin enable/disable toggling,
slash command catalog, script inspector, and deep reference guide reader.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BIND_HOST = "127.0.0.1"
PORT = int(os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT", "18767"))

APP_DATA_DIR = Path(
    os.environ.get(
        "ANTIGRAVITY_APP_DATA_DIR",
        str(Path.home() / ".gemini" / "antigravity"),
    )
)
CONFIG_DIR = Path.home() / ".gemini" / "config"
PLUGINS_DIR = Path(
    os.environ.get("ANTIGRAVITY_PLUGINS_DIR", str(CONFIG_DIR / "plugins"))
)
CONFIG_PATH = Path(
    os.environ.get("ANTIGRAVITY_CONFIG_PATH", str(CONFIG_DIR / "config.json"))
)
PRELOAD_PATH = APP_DATA_DIR / "lib" / "node_modules" / "sidecar_sdk" / "preload.js"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"plugins": {}, "sidecars": {}, "userSettings": {}}
    for attempt in range(3):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {"plugins": {}, "sidecars": {}, "userSettings": {}}
        except Exception:
            time.sleep(0.05)
    return {"plugins": {}, "sidecars": {}, "userSettings": {}}


def save_config(cfg: dict) -> bool:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CONFIG_PATH.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        # On Windows, retry briefly if another process (IDE file watcher) holds a shared handle
        for attempt in range(4):
            try:
                tmp_file.replace(CONFIG_PATH)
                return True
            except PermissionError:
                time.sleep(0.1)
        tmp_file.replace(CONFIG_PATH)
        return True
    except Exception as e:
        print(f"[skills-manager] Error saving config.json: {e}", file=sys.stderr)
        return False


def toggle_plugin_state(plugin_id: str, enabled: bool):
    if not plugin_id or not isinstance(plugin_id, str):
        return False, "Invalid pluginId parameter"

    # Safeguard: prevent disabling the active manager plugin from within its own UI
    if plugin_id == "skills-manager" and not enabled:
        return False, "skills-manager hosts this dashboard and cannot be disabled from within the UI."

    cfg = load_config()
    if "plugins" not in cfg or not isinstance(cfg["plugins"], dict):
        cfg["plugins"] = {}

    current = cfg["plugins"].get(plugin_id)
    if isinstance(current, dict):
        current["enabled"] = enabled
        cfg["plugins"][plugin_id] = current
    else:
        cfg["plugins"][plugin_id] = {"enabled": enabled}

    ok = save_config(cfg)
    return (True, f"Plugin {plugin_id} {'enabled' if enabled else 'disabled'}") if ok else (False, "Failed to write config.json")


def bulk_toggle_state(action: str):
    enable = (action == "enable_all")
    cfg = load_config()
    if "plugins" not in cfg or not isinstance(cfg["plugins"], dict):
        cfg["plugins"] = {}

    if PLUGINS_DIR.exists():
        for p in PLUGINS_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue

            # Safeguard: never disable skills-manager in bulk toggle
            if p.name == "skills-manager" and not enable:
                continue

            current = cfg["plugins"].get(p.name)
            if isinstance(current, dict):
                current["enabled"] = enable
                cfg["plugins"][p.name] = current
            else:
                cfg["plugins"][p.name] = {"enabled": enable}

    ok = save_config(cfg)
    return (True, f"Bulk update {action} successful") if ok else (False, "Failed to bulk update config.json")


def parse_skill_file(skill_dir: Path, skill_md: Path, plugin_id: str) -> dict:
    content = skill_md.read_text(encoding="utf-8", errors="replace")

    fm_name = skill_dir.name
    fm_desc = ""
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    body_text = content
    if fm_match:
        fm_raw, body_text = fm_match.groups()
        for line in fm_raw.splitlines():
            if line.startswith("name:"):
                val = line.split("name:", 1)[1].strip()
                if val:
                    fm_name = val
                break
        desc_m = re.search(r"description:\s*(?:>-|>|\|-|\||\"|')?\s*(.*?)(?=\n[a-z0-9_-]+:|\Z)", fm_raw, re.DOTALL)
        if desc_m:
            fm_desc = " ".join(desc_m.group(1).strip().split())
            fm_desc = fm_desc.strip('"\'')

    title_m = re.search(r"^#\s+(.+)$", body_text, re.MULTILINE)
    display_title = title_m.group(1).strip() if title_m else fm_name.replace("-", " ").title()

    # Detect legitimate slash command triggers
    detected_commands = []

    # 1. Check quoted commands in description (e.g. "/skills", "/skills-manager", "/usage-stats")
    for m in re.finditer(r'["\'](/[\w-]+)["\']', fm_desc):
        cmd = m.group(1)
        if not cmd.startswith(('/usr', '/etc', '/bin', '/var', '/tmp', '/dev', '/proc', '/sys', '/home', '/lib')):
            if cmd not in detected_commands:
                detected_commands.append(cmd)

    # 2. Check body for explicit slash command sections
    for m in re.finditer(r'(?:Quick Slash Command|Slash Command|Trigger on|Quick Command)[s]?:\s*(/[\w-]+)', body_text, re.IGNORECASE):
        cmd = m.group(1)
        if cmd not in detected_commands:
            detected_commands.append(cmd)

    # 3. Known custom skill slash commands
    KNOWN_COMMANDS = {
        "pentest": ["/pentest"],
        "superpowers": ["/superpowers"],
        "ui-design": ["/ui-design"],
        "documents": ["/documents"],
        "exam-prep": ["/exam-prep"],
        "prompt-optimizer": ["/prompt-optimizer"],
        "usage-stats": ["/usage-stats"],
        "skills-manager": ["/skills", "/skills-manager"],
    }
    if fm_name in KNOWN_COMMANDS:
        for c in KNOWN_COMMANDS[fm_name]:
            if c not in detected_commands:
                detected_commands.append(c)

    primary_cmd = detected_commands[0] if detected_commands else None

    # Classify trigger type accurately
    has_slash = len(detected_commands) > 0
    has_auto = any(k in fm_desc.lower() for k in ["trigger", "whenever", "intent", "use when", "activate", "mentions of", "mandatory", "search tool"])
    if has_slash and has_auto:
        trigger_type = "Hybrid (Slash & Auto)"
    elif has_slash:
        trigger_type = "Slash Command"
    else:
        trigger_type = "Auto-Activated"

    # Scan references
    refs_dir = skill_dir / "references"
    refs = []
    if refs_dir.is_dir():
        for rf in sorted(refs_dir.glob("*.md")):
            rf_text = rf.read_text(encoding="utf-8", errors="replace")[:1000]
            rf_title_m = re.search(r"^#\s+(.+)$", rf_text, re.MULTILINE)
            rf_title = rf_title_m.group(1).strip() if rf_title_m else rf.stem.replace("-", " ").title()
            refs.append({
                "name": rf.name,
                "title": rf_title,
                "sizeBytes": rf.stat().st_size,
                "relativePath": str(rf.relative_to(PLUGINS_DIR)).replace("\\", "/"),
            })

    # Scan scripts
    scripts_dir = skill_dir / "scripts"
    scripts = []
    if scripts_dir.is_dir():
        for sf in sorted(scripts_dir.iterdir()):
            if sf.is_file():
                scripts.append({
                    "name": sf.name,
                    "extension": sf.suffix.lstrip("."),
                    "sizeBytes": sf.stat().st_size,
                    "relativePath": str(sf.relative_to(PLUGINS_DIR)).replace("\\", "/"),
                })

    return {
        "name": fm_name,
        "displayName": display_title,
        "description": fm_desc or f"Skill {fm_name} providing specialized developer workflows.",
        "slashCommand": primary_cmd,
        "commandTriggers": detected_commands,
        "triggerType": trigger_type,
        "referencesCount": len(refs),
        "references": refs,
        "scriptsCount": len(scripts),
        "scripts": scripts,
        "path": str(skill_dir),
        "relativePath": str(skill_dir.relative_to(PLUGINS_DIR)).replace("\\", "/"),
        "skillMdRelative": str(skill_md.relative_to(PLUGINS_DIR)).replace("\\", "/"),
    }


def scan_plugins_and_skills() -> dict:
    cfg = load_config()
    cfg_plugins = cfg.get("plugins", {})
    if not isinstance(cfg_plugins, dict):
        cfg_plugins = {}

    plugins_list = []
    total_skills = 0
    total_refs = 0
    total_scripts = 0
    total_commands = 0
    active_plugins_count = 0
    disabled_plugins_count = 0

    if not PLUGINS_DIR.exists():
        return {"plugins": [], "stats": {}}

    for p in sorted(PLUGINS_DIR.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir() or p.name.startswith("."):
            continue

        plugin_id = p.name
        pj = p / "plugin.json"
        meta = {}
        if pj.exists():
            try:
                with open(pj, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        title = meta.get("title") or meta.get("displayName") or meta.get("name") or plugin_id.replace("-", " ").title()
        desc = meta.get("description", "")
        version = meta.get("version", "1.0.0")

        author = "Community"
        if "author" in meta:
            if isinstance(meta["author"], dict):
                author = meta["author"].get("name", "Community")
            elif isinstance(meta["author"], str):
                author = meta["author"]

        cfg_entry = cfg_plugins.get(plugin_id, {})
        is_official = False
        if isinstance(cfg_entry, dict) and "installedFrom" in cfg_entry:
            is_official = True
        elif author in ["Google", "Antigravity", "Anthropic"]:
            is_official = True

        # Enabled status
        if isinstance(cfg_entry, dict) and cfg_entry.get("enabled") is False:
            is_enabled = False
            disabled_plugins_count += 1
        else:
            is_enabled = True
            active_plugins_count += 1

        # Sidecars
        sidecars_dir = p / "sidecars"
        has_sidecar = False
        sidecar_details = []
        if sidecars_dir.is_dir():
            for sc in sorted(sidecars_dir.iterdir()):
                sc_json = sc / "sidecar.json"
                if sc.is_dir() and sc_json.is_file():
                    has_sidecar = True
                    sc_data = {}
                    try:
                        with open(sc_json, "r", encoding="utf-8") as f:
                            sc_data = json.load(f)
                    except Exception:
                        pass
                    sidecar_details.append({
                        "name": sc.name,
                        "displayName": sc_data.get("display_name", sc.name),
                        "description": sc_data.get("description", ""),
                        "hasWebUi": sc_data.get("has_web_ui", False),
                        "views": sc_data.get("ui_config", {}).get("views", []),
                        "relativePath": str(sc_json.relative_to(PLUGINS_DIR)).replace("\\", "/")
                    })

        # Skills
        skills_dir = p / "skills"
        skills = []
        if skills_dir.is_dir():
            for s in sorted(skills_dir.iterdir(), key=lambda x: x.name.lower()):
                skill_md = s / "SKILL.md"
                if not (s.is_dir() and skill_md.is_file()):
                    continue

                skill_info = parse_skill_file(s, skill_md, plugin_id)
                skills.append(skill_info)
                total_skills += 1
                total_refs += skill_info["referencesCount"]
                total_scripts += skill_info["scriptsCount"]
                total_commands += len(skill_info["commandTriggers"])

        plugins_list.append({
            "id": plugin_id,
            "name": plugin_id,
            "title": title,
            "description": desc,
            "version": version,
            "author": author,
            "isOfficial": is_official,
            "isHost": (plugin_id == "skills-manager"),
            "hasSidecar": has_sidecar,
            "sidecars": sidecar_details,
            "enabled": is_enabled,
            "path": str(p),
            "skillsCount": len(skills),
            "skills": skills,
            "suggestedPrompts": meta.get("suggestedPrompts", []),
        })

    stats = {
        "totalPlugins": len(plugins_list),
        "activePlugins": active_plugins_count,
        "disabledPlugins": disabled_plugins_count,
        "totalSkills": total_skills,
        "totalReferences": total_refs,
        "totalScripts": total_scripts,
        "totalCommands": total_commands,
        "serverPort": PORT,
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "configPath": str(CONFIG_PATH),
    }

    return {"plugins": plugins_list, "stats": stats}


def read_document_content(rel_or_abs_path: str, base_dir_hint: str = ""):
    raw = rel_or_abs_path.strip()
    if raw.startswith("file:///"):
        raw = raw[8:]
    elif raw.startswith("file://"):
        raw = raw[7:]

    raw = unquote(raw)
    p = Path(raw)

    plugins_resolved = PLUGINS_DIR.resolve()

    if not p.is_absolute():
        if base_dir_hint:
            candidate = (PLUGINS_DIR / base_dir_hint / p).resolve()
            if candidate.is_file():
                p = candidate
            else:
                p = (PLUGINS_DIR / p).resolve()
        else:
            p = (PLUGINS_DIR / p).resolve()
    else:
        p = p.resolve()

    # Security check: must reside strictly inside PLUGINS_DIR
    try:
        p.relative_to(plugins_resolved)
    except ValueError:
        return None, "Forbidden: Path is outside plugins directory"

    if not p.is_file():
        return None, "File not found"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        rel_path = str(p.relative_to(plugins_resolved)).replace("\\", "/")
        rel_dir = str(p.parent.relative_to(plugins_resolved)).replace("\\", "/")
        return {
            "name": p.name,
            "path": str(p),
            "relativePath": rel_path,
            "relativeDir": rel_dir,
            "sizeBytes": p.stat().st_size,
            "content": content,
        }, None
    except Exception as e:
        return None, str(e)


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Skills & Plugin Hub</title>
  <script src="/preload.js"></script>
  <style>
    :root {
      --bg: #070b14;
      --card-bg: #0f172a;
      --card-inner: #131d35;
      --border: rgba(255, 255, 255, 0.08);
      --border-hover: rgba(99, 102, 241, 0.4);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --accent-emerald: #10b981;
      --accent-emerald-dim: rgba(16, 185, 129, 0.12);
      --accent-amber: #f59e0b;
      --accent-amber-dim: rgba(245, 158, 11, 0.12);
      --accent-cyan: #06b6d4;
      --accent-cyan-dim: rgba(6, 182, 212, 0.12);
      --accent-rose: #f43f5e;
      --accent-rose-dim: rgba(244, 63, 94, 0.12);
      --accent-purple: #a855f7;
      --accent-purple-dim: rgba(168, 85, 247, 0.12);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-sub: #64748b;
      --radius: 12px;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", sans-serif;
      font-size: 13px;
      line-height: 1.5;
      min-height: 100vh;
      overflow-y: scroll;
    }

    .container {
      max-width: 1140px;
      margin: 0 auto;
      padding: 20px 16px 80px 16px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Top Navigation / Brand Header */
    .top-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }

    .brand-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, #1e1b4b, #312e81);
      border: 1px solid rgba(99, 102, 241, 0.35);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.2);
    }

    .brand-title {
      font-size: 18px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-sub {
      font-size: 11px;
      color: var(--text-muted);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Standard Button Styles */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 8px;
      cursor: pointer;
      border: 1px solid var(--border);
      background: var(--card-bg);
      color: var(--text-main);
      transition: all 0.15s ease;
      text-decoration: none;
    }
    .btn:hover {
      background: #1e293b;
      border-color: rgba(255, 255, 255, 0.2);
    }
    .btn-primary {
      background: var(--primary);
      border-color: var(--primary-hover);
      color: #fff;
    }
    .btn-primary:hover {
      background: var(--primary-hover);
    }
    .btn-sm {
      padding: 4px 8px;
      font-size: 11px;
      border-radius: 6px;
    }

    /* Bento Stats Cards */
    .bento-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
    }

    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s ease;
    }
    .stat-card:hover {
      border-color: var(--border-hover);
    }
    .stat-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: linear-gradient(90deg, #6366f1, #06b6d4);
    }
    .stat-card.emerald::before { background: linear-gradient(90deg, #10b981, #06b6d4); }
    .stat-card.amber::before { background: linear-gradient(90deg, #f59e0b, #ef4444); }
    .stat-card.cyan::before { background: linear-gradient(90deg, #06b6d4, #6366f1); }

    .stat-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .stat-val {
      font-size: 26px;
      font-weight: 700;
      color: #fff;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
    }
    .stat-desc {
      font-size: 11px;
      color: var(--text-sub);
    }

    /* Filter & Search Bar */
    .toolbar {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 10px 14px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .search-box {
      flex: 1 1 260px;
      display: flex;
      align-items: center;
      background: #090e1a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px 12px;
      gap: 8px;
      transition: border-color 0.15s ease;
    }
    .search-box:focus-within {
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
    }
    .search-input {
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-size: 12px;
      width: 100%;
    }
    .search-input::placeholder {
      color: var(--text-sub);
    }

    .filter-tabs {
      display: flex;
      align-items: center;
      gap: 4px;
      flex-wrap: wrap;
    }

    .tab-chip {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 500;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .tab-chip:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.05);
    }
    .tab-chip.active {
      background: rgba(99, 102, 241, 0.15);
      border-color: rgba(99, 102, 241, 0.4);
      color: #a5b4fc;
      font-weight: 600;
    }

    .bulk-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* Plugin Card Grid */
    .plugins-grid {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .plugin-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 0;
      transition: border-color 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease;
    }
    .plugin-card:hover {
      border-color: rgba(255, 255, 255, 0.2);
    }
    .plugin-card.is-disabled {
      border-color: rgba(244, 63, 94, 0.25);
      background: rgba(15, 23, 42, 0.6);
      opacity: 0.75;
    }
    .plugin-card.is-disabled:hover {
      opacity: 0.95;
    }
    .plugin-card.is-host {
      border-color: rgba(99, 102, 241, 0.35);
      background: linear-gradient(180deg, #10172e, #0f172a);
    }

    /* Plugin Header Row */
    .plugin-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      cursor: pointer;
      user-select: none;
      padding: 2px 0;
      border-radius: 6px;
      transition: color 0.15s ease;
    }
    .plugin-header:hover .plugin-title {
      color: #38bdf8;
    }

    .plugin-title-area {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      flex: 1 1 auto;
      min-width: 0;
    }

    .plugin-header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }

    .expand-chevron {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s ease;
      flex-shrink: 0;
      padding: 0;
    }
    .plugin-card:hover .expand-chevron {
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.16);
    }
    .plugin-card.is-open .expand-chevron {
      transform: rotate(180deg);
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.12);
      border-color: rgba(56, 189, 248, 0.3);
    }

    .plugin-body {
      display: flex;
      flex-direction: column;
      gap: 14px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      animation: fadeIn 0.18s ease-out;
    }
    .plugin-card.is-collapsed .plugin-body {
      display: none;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .plugin-avatar {
      width: 42px;
      height: 42px;
      border-radius: 10px;
      background: #19233c;
      border: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: 700;
      color: #a5b4fc;
      flex-shrink: 0;
    }

    .plugin-meta-info {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    .plugin-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .plugin-title {
      font-size: 15px;
      font-weight: 700;
      color: #fff;
    }

    .plugin-id-tag {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.05);
      padding: 1px 6px;
      border-radius: 4px;
    }

    .plugin-badges {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .badge {
      font-size: 10px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.02em;
    }
    .badge-official {
      background: var(--accent-cyan-dim);
      color: var(--accent-cyan);
      border: 1px solid rgba(6, 182, 212, 0.3);
    }
    .badge-host {
      background: rgba(99, 102, 241, 0.15);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.4);
    }
    .badge-sidecar {
      background: var(--accent-purple-dim);
      color: #c084fc;
      border: 1px solid rgba(168, 85, 247, 0.3);
    }
    .badge-enabled {
      background: var(--accent-emerald-dim);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-disabled {
      background: var(--accent-rose-dim);
      color: var(--accent-rose);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }

    .plugin-subinfo {
      font-size: 11px;
      color: var(--text-sub);
    }

    /* Switch Toggle */
    .switch-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .switch-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
    }
    .switch {
      position: relative;
      display: inline-block;
      width: 44px;
      height: 24px;
    }
    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #334155;
      transition: 0.25s;
      border-radius: 24px;
    }
    .slider:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: 0.25s;
      border-radius: 50%;
    }
    input:checked + .slider {
      background-color: var(--accent-emerald);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.35);
    }
    input:checked + .slider:before {
      transform: translateX(20px);
    }
    .switch.is-locked .slider {
      cursor: not-allowed;
      opacity: 0.85;
    }

    .plugin-description {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
    }

    /* Sidecars section */
    .sidecars-section {
      background: rgba(168, 85, 247, 0.05);
      border: 1px solid rgba(168, 85, 247, 0.2);
      border-radius: 10px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .sidecars-header-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-weight: 600;
      color: #c084fc;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .sidecar-item-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 6px;
      padding: 8px 10px;
    }

    /* Skills Inside Plugin */
    .skills-section {
      background: var(--card-inner);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 10px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .skills-header-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      padding-bottom: 6px;
    }

    .skill-item {
      background: #0d1527;
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: border-color 0.15s ease;
    }
    .skill-item:hover {
      border-color: rgba(99, 102, 241, 0.3);
    }

    .skill-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .skill-name-group {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .skill-name {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
    }

    /* Command Chip with One-Click Copy */
    .command-chip {
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.35);
      color: #fbbf24;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
      user-select: none;
    }
    .command-chip:hover {
      background: rgba(245, 158, 11, 0.24);
      border-color: #f59e0b;
      transform: translateY(-1px);
    }
    .command-chip:active {
      transform: translateY(0);
    }

    .trigger-badge {
      font-size: 10px;
      font-weight: 500;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.02em;
    }
    .trigger-auto {
      background: var(--accent-cyan-dim);
      color: var(--accent-cyan);
      border: 1px solid rgba(6, 182, 212, 0.3);
    }
    .trigger-slash {
      background: var(--accent-amber-dim);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .trigger-hybrid {
      background: rgba(99, 102, 241, 0.12);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.3);
    }

    .skill-desc {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
    }

    .skill-footer-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 4px;
      padding-top: 8px;
      border-top: 1px solid rgba(255, 255, 255, 0.04);
    }

    .skill-path-code {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-sub);
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.2);
    }
    .skill-path-code:hover {
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.05);
    }

    .skill-actions-group {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .guides-pill {
      background: var(--accent-cyan-dim);
      border: 1px solid rgba(6, 182, 212, 0.3);
      color: #38bdf8;
      font-size: 11px;
      font-weight: 500;
      padding: 3px 8px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
    }
    .guides-pill:hover {
      background: rgba(6, 182, 212, 0.2);
    }

    .scripts-pill {
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #a5b4fc;
      font-size: 11px;
      font-weight: 500;
      padding: 3px 8px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
    }
    .scripts-pill:hover {
      background: rgba(99, 102, 241, 0.22);
    }

    /* Sub-Guides / Scripts Drawers inside Skill */
    .guides-drawer, .scripts-drawer {
      display: none;
      background: #080d1a;
      border: 1px dashed rgba(6, 182, 212, 0.3);
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: 8px;
      flex-direction: column;
      gap: 6px;
    }
    .scripts-drawer {
      border-color: rgba(99, 102, 241, 0.3);
    }
    .guides-drawer.open, .scripts-drawer.open {
      display: flex;
    }

    .drawer-title {
      font-size: 11px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .drawer-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      background: rgba(255, 255, 255, 0.02);
      border-radius: 6px;
      font-size: 11px;
      gap: 10px;
    }
    .drawer-item:hover {
      background: rgba(255, 255, 255, 0.06);
    }

    .drawer-name-link {
      color: #f1f5f9;
      cursor: pointer;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .drawer-name-link:hover {
      color: #38bdf8;
      text-decoration: underline;
    }

    /* Empty state */
    .empty-state {
      text-align: center;
      padding: 48px 16px;
      background: var(--card-bg);
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      color: var(--text-muted);
    }

    /* Document Reader Modal */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(3, 7, 18, 0.85);
      backdrop-filter: blur(8px);
      z-index: 9999;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-overlay.open {
      display: flex;
    }

    .modal-container {
      background: #0b1120;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 14px;
      width: 100%;
      max-width: 880px;
      max-height: 88vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      overflow: hidden;
      animation: modalFadeIn 0.18s ease-out;
    }
    @keyframes modalFadeIn {
      from { opacity: 0; transform: scale(0.97); }
      to { opacity: 1; transform: scale(1); }
    }

    .modal-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0f172a;
      gap: 12px;
    }
    .modal-title-wrap {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .modal-title {
      font-size: 15px;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .modal-subtitle {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-sub);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .modal-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }

    .modal-body {
      padding: 24px 28px;
      overflow-y: auto;
      font-size: 13px;
      line-height: 1.65;
      color: #e2e8f0;
    }

    /* Markdown Reader Styling */
    .md-content h1 { font-size: 20px; color: #fff; margin: 0 0 12px 0; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); }
    .md-content h2 { font-size: 16px; color: #f8fafc; margin: 20px 0 8px 0; }
    .md-content h3 { font-size: 14px; color: #cbd5e1; margin: 16px 0 6px 0; }
    .md-content h4 { font-size: 13px; color: #94a3b8; margin: 12px 0 4px 0; font-weight: 600; }
    .md-content p { margin-bottom: 12px; }
    .md-content ul, .md-content ol { margin: 8px 0 14px 22px; }
    .md-content li { margin-bottom: 4px; }
    .md-content pre {
      background: #030712;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 12px 14px;
      overflow-x: auto;
      margin: 12px 0 16px 0;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.5;
    }
    .md-content code {
      font-family: var(--font-mono);
      background: rgba(255, 255, 255, 0.08);
      padding: 2px 5px;
      border-radius: 4px;
      font-size: 12px;
      color: #38bdf8;
    }
    .md-content pre code {
      background: transparent;
      padding: 0;
      color: #f1f5f9;
    }
    .md-content blockquote {
      border-left: 3px solid var(--primary);
      padding: 6px 12px;
      background: rgba(99, 102, 241, 0.06);
      border-radius: 0 6px 6px 0;
      color: var(--text-muted);
      margin: 12px 0;
      font-style: italic;
    }
    .md-content .table-wrap {
      overflow-x: auto;
      margin: 14px 0;
    }
    .md-content table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .md-content th, .md-content td {
      border: 1px solid rgba(255, 255, 255, 0.08);
      padding: 8px 12px;
      text-align: left;
    }
    .md-content th {
      background: #1e293b;
      color: #fff;
      font-weight: 600;
    }
    .md-content tr:nth-child(even) {
      background: rgba(255, 255, 255, 0.02);
    }
    .md-content a.doc-link {
      color: #38bdf8;
      text-decoration: underline;
      cursor: pointer;
    }
    .md-content a.doc-link:hover {
      color: #7dd3fc;
    }
    .md-content a.ext-link {
      color: #a5b4fc;
      text-decoration: none;
    }
    .md-content a.ext-link:hover {
      text-decoration: underline;
    }

    /* Toast Notification */
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e293b;
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
      transform: translateY(80px);
      opacity: 0;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 10000;
      pointer-events: none;
    }
    .toast.show {
      transform: translateY(0);
      opacity: 1;
    }
    .toast.success { border-color: rgba(16, 185, 129, 0.4); color: #34d399; }
    .toast.error { border-color: rgba(244, 63, 94, 0.4); color: #fb7185; }

    /* Responsive */
    @media (max-width: 600px) {
      .container { padding: 12px 10px 60px 10px; }
      .bento-stats { grid-template-columns: 1fr 1fr; }
      .plugin-header { flex-direction: column; align-items: flex-start; gap: 10px; }
      .plugin-title-area { flex: 0 0 auto; width: 100%; }
      .plugin-header-actions { width: 100%; justify-content: space-between; padding-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
    }
  </style>
</head>
<body>

<div class="container">
  <!-- Top Navigation Header -->
  <header class="top-header">
    <div class="brand-group">
      <div class="brand-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#a5b4fc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div>
        <div class="brand-title">
          Skills & Plugin Hub
        </div>
        <div class="brand-sub">Manage, inspect, and toggle Antigravity agent capabilities</div>
      </div>
    </div>

    <div class="header-actions">
      <button class="btn btn-sm" id="refreshBtn" onclick="loadData()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19"/>
        </svg>
        Refresh
      </button>
      <a class="btn btn-sm" href="/" target="_blank" title="Open full tab in browser">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
        </svg>
        Aux View
      </a>
    </div>
  </header>

  <!-- Bento Stats Row -->
  <section class="bento-stats">
    <div class="stat-card emerald">
      <div class="stat-label">
        <span>Installed Plugins</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      </div>
      <div class="stat-val" id="statTotalPlugins">--</div>
      <div class="stat-desc" id="statPluginBreakdown">-- Active · -- Disabled</div>
    </div>

    <div class="stat-card cyan">
      <div class="stat-label">
        <span>Active Skills</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      </div>
      <div class="stat-val" id="statTotalSkills">--</div>
      <div class="stat-desc">Custom & Official Playbooks</div>
    </div>

    <div class="stat-card amber">
      <div class="stat-label">
        <span>Slash Commands</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      </div>
      <div class="stat-val" id="statTotalCommands">--</div>
      <div class="stat-desc">One-click copy to prompt</div>
    </div>

    <div class="stat-card">
      <div class="stat-label">
        <span>Reference Guides & Scripts</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      </div>
      <div class="stat-val" id="statTotalDocs">--</div>
      <div class="stat-desc" id="statScriptsBreakdown">-- Markdown Guides · -- Scripts</div>
    </div>
  </section>

  <!-- Filter & Search Toolbar -->
  <section class="toolbar">
    <div class="search-box">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <input type="text" class="search-input" id="searchInput" placeholder="Search skills, commands (/pentest), plugins, guides... (Press / to focus)" oninput="handleSearch()"/>
    </div>

    <div class="filter-tabs">
      <button class="tab-chip active" data-filter="all" onclick="setFilter('all')">All</button>
      <button class="tab-chip" data-filter="active" onclick="setFilter('active')">Enabled</button>
      <button class="tab-chip" data-filter="disabled" onclick="setFilter('disabled')">Disabled</button>
      <button class="tab-chip" data-filter="custom" onclick="setFilter('custom')">Custom</button>
      <button class="tab-chip" data-filter="official" onclick="setFilter('official')">Official</button>
      <button class="tab-chip" data-filter="commands" onclick="setFilter('commands')">Commands</button>
      <button class="tab-chip" data-filter="auto" onclick="setFilter('auto')">Auto-Activated</button>
    </div>

    <div class="bulk-actions">
      <button class="btn btn-sm" id="expandCollapseAllBtn" onclick="toggleExpandAll()" title="Expand or collapse all plugin details">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"></polyline><polyline points="7 6 12 11 17 6"></polyline></svg>
        Expand All
      </button>
      <button class="btn btn-sm" onclick="bulkToggle('enable_all')" title="Enable all installed plugins">Enable All</button>
      <button class="btn btn-sm" onclick="bulkToggle('disable_all')" title="Disable all plugins (skills-manager remains active)">Disable All</button>
    </div>
  </section>

  <!-- Plugins Bento List -->
  <main class="plugins-grid" id="pluginsGrid">
    <div class="empty-state">Loading plugins and skills...</div>
  </main>
</div>

<!-- Document Reader Modal -->
<div class="modal-overlay" id="docModal" onclick="closeModalOnBackdrop(event)">
  <div class="modal-container" role="dialog" aria-modal="true">
    <div class="modal-header">
      <div class="modal-title-wrap">
        <div class="modal-title" id="modalDocTitle">Document Title</div>
        <div class="modal-subtitle" id="modalDocPath">path/to/file.md</div>
      </div>
      <div class="modal-header-actions">
        <button class="btn btn-sm" id="modalBackBtn" style="display:none;" onclick="navigateDocBack()">
          ← Back
        </button>
        <button class="btn btn-sm" onclick="copyModalContent()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy Content
        </button>
        <button class="btn btn-sm" onclick="closeModal()">
          ✕
        </button>
      </div>
    </div>
    <div class="modal-body md-content" id="modalDocBody">
      Loading...
    </div>
  </div>
</div>

<!-- Toast Notification -->
<div class="toast" id="toast">Copied to clipboard</div>

<script>
  let ALL_PLUGINS = [];
  let STATS = {};
  let CURRENT_FILTER = "all";
  let SEARCH_QUERY = "";
  let CURRENT_MODAL_RAW = "";
  let CURRENT_DOC_PATH = "";
  let CURRENT_DOC_TITLE = "";
  let CURRENT_DOC_DIR = "";
  const DOC_HISTORY_STACK = [];
  const OPEN_PLUGINS = new Set();

  async function loadData() {
    const refreshBtn = document.getElementById("refreshBtn");
    if (refreshBtn) refreshBtn.style.opacity = "0.5";
    try {
      const res = await fetch("/api/plugins");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      ALL_PLUGINS = data.plugins || [];
      STATS = data.stats || {};
      renderStats();
      renderPlugins();
    } catch (err) {
      showToast("Error loading plugins: " + err.message, "error");
    } finally {
      if (refreshBtn) refreshBtn.style.opacity = "1";
    }
  }

  function renderStats() {
    document.getElementById("statTotalPlugins").textContent = STATS.totalPlugins ?? "--";
    document.getElementById("statPluginBreakdown").textContent = `${STATS.activePlugins ?? 0} Enabled · ${STATS.disabledPlugins ?? 0} Disabled`;
    document.getElementById("statTotalSkills").textContent = STATS.totalSkills ?? "--";
    document.getElementById("statTotalCommands").textContent = STATS.totalCommands ?? "--";
    document.getElementById("statTotalDocs").textContent = (STATS.totalReferences ?? 0) + (STATS.totalScripts ?? 0);
    document.getElementById("statScriptsBreakdown").textContent = `${STATS.totalReferences ?? 0} Markdown Guides · ${STATS.totalScripts ?? 0} Scripts`;
  }

  function setFilter(filter) {
    CURRENT_FILTER = filter;
    document.querySelectorAll(".tab-chip").forEach(chip => {
      chip.classList.toggle("active", chip.getAttribute("data-filter") === filter);
    });
    renderPlugins();
  }

  function handleSearch() {
    SEARCH_QUERY = document.getElementById("searchInput").value.trim().toLowerCase();
    renderPlugins();
  }

  function filterMatch(p) {
    // Filter tab
    if (CURRENT_FILTER === "active" && !p.enabled) return false;
    if (CURRENT_FILTER === "disabled" && p.enabled) return false;
    if (CURRENT_FILTER === "custom" && p.isOfficial) return false;
    if (CURRENT_FILTER === "official" && !p.isOfficial) return false;
    if (CURRENT_FILTER === "commands") {
      const hasCmd = p.skills.some(s => s.commandTriggers && s.commandTriggers.length > 0);
      if (!hasCmd) return false;
    }
    if (CURRENT_FILTER === "auto") {
      const hasAuto = p.skills.some(s => s.triggerType.includes("Auto"));
      if (!hasAuto) return false;
    }

    // Search query
    if (!SEARCH_QUERY) return true;
    const query = SEARCH_QUERY;

    const matchesName = p.name.toLowerCase().includes(query) || p.title.toLowerCase().includes(query);
    const matchesDesc = (p.description || "").toLowerCase().includes(query);
    const matchesSkills = p.skills.some(s =>
      s.name.toLowerCase().includes(query) ||
      (s.displayName || "").toLowerCase().includes(query) ||
      (s.description || "").toLowerCase().includes(query) ||
      (s.commandTriggers || []).some(cmd => cmd.toLowerCase().includes(query)) ||
      (s.references || []).some(r => r.name.toLowerCase().includes(query) || r.title.toLowerCase().includes(query)) ||
      (s.scripts || []).some(sc => sc.name.toLowerCase().includes(query))
    );

    return matchesName || matchesDesc || matchesSkills;
  }

  function renderPlugins() {
    // Preserve any open drawers
    const openDrawers = new Set(
      Array.from(document.querySelectorAll('.guides-drawer.open, .scripts-drawer.open')).map(el => el.id)
    );

    const container = document.getElementById("pluginsGrid");
    const filtered = ALL_PLUGINS.filter(filterMatch);

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 4px;">No matching skills or plugins found</p>
          <p>Try refining your search query or switching the filter tab.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(p => {
      const iconLetter = p.title ? p.title.charAt(0).toUpperCase() : p.name.charAt(0).toUpperCase();

      const skillsHtml = p.skills.map(s => {
        // Render all command chips
        const commandChips = (s.commandTriggers || []).map(cmd => `
          <div class="command-chip" data-copy="${escapeHtml(cmd)}" onclick="copyText(this.dataset.copy, 'Copied command ${escapeHtml(cmd)}!')" title="Click to copy slash command">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            ${escapeHtml(cmd)}
          </div>
        `).join("");

        // Trigger type badge
        let triggerClass = "trigger-badge trigger-auto";
        if (s.triggerType.includes("Hybrid")) triggerClass = "trigger-badge trigger-hybrid";
        else if (s.triggerType.includes("Slash")) triggerClass = "trigger-badge trigger-slash";

        const refsCountPill = s.referencesCount > 0 ? `
          <div class="guides-pill" onclick="toggleDrawer('${p.id}-${s.name}-guides')" title="View reference guides">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
            ${s.referencesCount} Guides
          </div>
        ` : '';

        const scriptsPill = s.scriptsCount > 0 ? `
          <div class="scripts-pill" onclick="toggleDrawer('${p.id}-${s.name}-scripts')" title="View bundled scripts">
            ⚡ ${s.scriptsCount} Scripts
          </div>
        ` : '';

        const guidesList = (s.references || []).map(r => `
          <div class="drawer-item">
            <span class="drawer-name-link" data-doc="${escapeHtml(r.relativePath)}" data-title="${escapeHtml(r.title)}" onclick="openDoc(this.dataset.doc, this.dataset.title)">
              📄 ${escapeHtml(r.title)} <span style="color:#64748b; font-size:10px;">(${escapeHtml(r.name)})</span>
            </span>
            <button class="btn btn-sm" data-doc="${escapeHtml(r.relativePath)}" data-title="${escapeHtml(r.title)}" onclick="openDoc(this.dataset.doc, this.dataset.title)">Read</button>
          </div>
        `).join("");

        const scriptsList = (s.scripts || []).map(sc => `
          <div class="drawer-item">
            <span class="drawer-name-link" data-doc="${escapeHtml(sc.relativePath)}" data-title="${escapeHtml(sc.name)}" onclick="openDoc(this.dataset.doc, this.dataset.title)">
              ⚡ ${escapeHtml(sc.name)} <span style="color:#64748b; font-size:10px;">(${(sc.sizeBytes / 1024).toFixed(1)} KB)</span>
            </span>
            <button class="btn btn-sm" data-doc="${escapeHtml(sc.relativePath)}" data-title="${escapeHtml(sc.name)}" onclick="openDoc(this.dataset.doc, this.dataset.title)">View Script</button>
          </div>
        `).join("");

        return `
          <div class="skill-item">
            <div class="skill-title-row">
              <div class="skill-name-group">
                <span class="skill-name">${escapeHtml(s.displayName)}</span>
                ${commandChips}
                <span class="${triggerClass}">${escapeHtml(s.triggerType)}</span>
              </div>
              <div class="skill-actions-group">
                ${refsCountPill}
                ${scriptsPill}
                <button class="btn btn-sm" data-doc="${escapeHtml(s.skillMdRelative)}" data-title="${escapeHtml(s.displayName)} - SKILL.md" onclick="openDoc(this.dataset.doc, this.dataset.title)">
                  View SKILL.md
                </button>
              </div>
            </div>

            <div class="skill-desc">${escapeHtml(s.description)}</div>

            <div class="skill-footer-row">
              <div class="skill-path-code" data-copy="${escapeHtml(s.path)}" onclick="copyText(this.dataset.copy, 'Copied skill absolute path!')" title="Click to copy path">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                ${escapeHtml(s.relativePath)}
              </div>
            </div>

            <!-- Expandable Drawer for References -->
            ${s.referencesCount > 0 ? `
              <div class="guides-drawer" id="${p.id}-${s.name}-guides">
                <div class="drawer-title" style="color:#38bdf8;">
                  <span>Bundled Reference Documentation</span>
                  <span style="font-size:10px; color:#64748b;">${s.referencesCount} files</span>
                </div>
                ${guidesList}
              </div>
            ` : ''}

            <!-- Expandable Drawer for Scripts -->
            ${s.scriptsCount > 0 ? `
              <div class="scripts-drawer" id="${p.id}-${s.name}-scripts">
                <div class="drawer-title" style="color:#a5b4fc;">
                  <span>Bundled Automation Scripts</span>
                  <span style="font-size:10px; color:#64748b;">${s.scriptsCount} scripts</span>
                </div>
                ${scriptsList}
              </div>
            ` : ''}
          </div>
        `;
      }).join("");

      // Sidecars section if plugin has sidecars
      const sidecarsHtml = (p.sidecars && p.sidecars.length > 0) ? `
        <div class="sidecars-section">
          <div class="sidecars-header-bar">
            <span>Integrated Background Sidecar</span>
            <span>Aux Pane UI</span>
          </div>
          ${p.sidecars.map(sc => `
            <div class="sidecar-item-row">
              <div>
                <span style="font-weight:600; color:#fff;">${escapeHtml(sc.displayName)}</span>
                <span class="plugin-id-tag" style="margin-left:6px;">${escapeHtml(sc.name)}</span>
                <div style="font-size:11px; color:#94a3b8; margin-top:2px;">${escapeHtml(sc.description)}</div>
              </div>
              <button class="btn btn-sm" data-doc="${escapeHtml(sc.relativePath)}" data-title="${escapeHtml(sc.name)} - sidecar.json" onclick="openDoc(this.dataset.doc, this.dataset.title)">
                View sidecar.json
              </button>
            </div>
          `).join("")}
        </div>
      ` : '';

      const isOpen = OPEN_PLUGINS.has(p.id) || (SEARCH_QUERY && SEARCH_QUERY.length > 0);

      return `
        <article class="plugin-card ${p.enabled ? '' : 'is-disabled'} ${p.isHost ? 'is-host' : ''} ${isOpen ? 'is-open' : 'is-collapsed'}" id="card-${p.id}">
          <div class="plugin-header" onclick="togglePluginDetails('${p.id}')">
            <div class="plugin-title-area">
              <div class="plugin-avatar">${iconLetter}</div>
              <div class="plugin-meta-info">
                <div class="plugin-title-row">
                  <span class="plugin-title">${escapeHtml(p.title)}</span>
                  <span class="plugin-id-tag">${escapeHtml(p.id)}</span>
                  <div class="plugin-badges">
                    ${p.isHost ? '<span class="badge badge-host">Host Manager</span>' : ''}
                    ${p.isOfficial ? '<span class="badge badge-official">Official</span>' : ''}
                    ${p.hasSidecar ? '<span class="badge badge-sidecar">Sidecar UI</span>' : ''}
                    <span class="badge ${p.enabled ? 'badge-enabled' : 'badge-disabled'}" id="badge-${p.id}">
                      ${p.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>
                <div class="plugin-subinfo">
                  v${escapeHtml(p.version)} · By ${escapeHtml(p.author)} · ${p.skillsCount} ${p.skillsCount === 1 ? 'Skill' : 'Skills'}
                </div>
              </div>
            </div>

            <div class="plugin-header-actions" onclick="event.stopPropagation()">
              <div class="switch-wrap">
                <span class="switch-label" id="label-${p.id}">${p.enabled ? 'ACTIVE' : 'OFF'}</span>
                <label class="switch ${p.isHost ? 'is-locked' : ''}">
                  <input type="checkbox" ${p.enabled ? 'checked' : ''} ${p.isHost ? 'disabled' : ''} onchange="togglePlugin('${p.id}', this.checked)">
                  <span class="slider" ${p.isHost ? 'title="skills-manager is the active manager and cannot be disabled from within the UI"' : ''}></span>
                </label>
              </div>
              <button class="expand-chevron" onclick="event.stopPropagation(); togglePluginDetails('${p.id}')" title="Toggle plugin details">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
              </button>
            </div>
          </div>

          <div class="plugin-body" id="body-${p.id}">
            <div class="plugin-description">${escapeHtml(p.description || 'No description provided.')}</div>

            ${sidecarsHtml}

            ${p.skillsCount > 0 ? `
              <div class="skills-section">
                <div class="skills-header-bar">
                  <span>Included Skills & Capabilities</span>
                  <span>${p.skillsCount} Registered</span>
                </div>
                ${skillsHtml}
              </div>
            ` : (p.hasSidecar ? '' : `
              <div style="font-size:11px; color:#64748b; font-style:italic;">
                This plugin operates as a background tool without standalone skills.
              </div>
            `)}
          </div>
        </article>
      `;
    }).join("");

    // Restore drawer states
    openDrawers.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.add("open");
    });

    updateExpandAllBtnText();
  }

  function togglePluginDetails(pluginId) {
    const card = document.getElementById(`card-${pluginId}`);
    if (!card) return;

    if (OPEN_PLUGINS.has(pluginId)) {
      OPEN_PLUGINS.delete(pluginId);
      card.classList.remove("is-open");
      card.classList.add("is-collapsed");
    } else {
      OPEN_PLUGINS.add(pluginId);
      card.classList.remove("is-collapsed");
      card.classList.add("is-open");
    }
    updateExpandAllBtnText();
  }

  function toggleExpandAll() {
    const allCards = document.querySelectorAll(".plugin-card");
    const anyClosed = Array.from(allCards).some(c => c.classList.contains("is-collapsed"));

    if (anyClosed) {
      ALL_PLUGINS.forEach(p => OPEN_PLUGINS.add(p.id));
      allCards.forEach(c => {
        c.classList.remove("is-collapsed");
        c.classList.add("is-open");
      });
    } else {
      OPEN_PLUGINS.clear();
      allCards.forEach(c => {
        c.classList.remove("is-open");
        c.classList.add("is-collapsed");
      });
    }
    updateExpandAllBtnText();
  }

  function updateExpandAllBtnText() {
    const btn = document.getElementById("expandCollapseAllBtn");
    if (!btn) return;
    const allCards = document.querySelectorAll(".plugin-card");
    const anyClosed = Array.from(allCards).some(c => c.classList.contains("is-collapsed"));
    btn.innerHTML = anyClosed ? `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"></polyline><polyline points="7 6 12 11 17 6"></polyline></svg>
      Expand All
    ` : `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 11 12 6 7 11"></polyline><polyline points="17 18 12 13 7 18"></polyline></svg>
      Collapse All
    `;
  }

  function toggleDrawer(drawerId) {
    const el = document.getElementById(drawerId);
    if (el) el.classList.toggle("open");
  }

  async function togglePlugin(pluginId, isEnabled) {
    if (pluginId === "skills-manager" && !isEnabled) {
      showToast("Cannot disable skills-manager while the manager is active.", "error");
      const cb = document.querySelector(`#card-${pluginId} input[type="checkbox"]`);
      if (cb) cb.checked = true;
      return;
    }

    // Targeted DOM update
    const card = document.getElementById(`card-${pluginId}`);
    const badge = document.getElementById(`badge-${pluginId}`);
    const label = document.getElementById(`label-${pluginId}`);

    if (card) card.classList.toggle("is-disabled", !isEnabled);
    if (badge) {
      badge.className = `badge ${isEnabled ? 'badge-enabled' : 'badge-disabled'}`;
      badge.textContent = isEnabled ? 'Enabled' : 'Disabled';
    }
    if (label) label.textContent = isEnabled ? 'ACTIVE' : 'OFF';

    // Update in-memory state
    const p = ALL_PLUGINS.find(item => item.id === pluginId);
    if (p) p.enabled = isEnabled;

    // Update stats counters smoothly
    const activeCount = ALL_PLUGINS.filter(item => item.enabled).length;
    const disabledCount = ALL_PLUGINS.length - activeCount;
    document.getElementById("statPluginBreakdown").textContent = `${activeCount} Enabled · ${disabledCount} Disabled`;

    try {
      const res = await fetch("/api/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pluginId, enabled: isEnabled })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || "Toggle failed");
      showToast(`${pluginId} ${isEnabled ? 'Enabled' : 'Disabled'}`);
    } catch (err) {
      showToast("Error updating plugin: " + err.message, "error");
      // Revert in-memory and UI
      if (p) p.enabled = !isEnabled;
      if (card) card.classList.toggle("is-disabled", isEnabled);
      if (badge) {
        badge.className = `badge ${!isEnabled ? 'badge-enabled' : 'badge-disabled'}`;
        badge.textContent = !isEnabled ? 'Enabled' : 'Disabled';
      }
      if (label) label.textContent = !isEnabled ? 'ACTIVE' : 'OFF';
      const cb = document.querySelector(`#card-${pluginId} input[type="checkbox"]`);
      if (cb) cb.checked = !isEnabled;
    }
  }

  async function bulkToggle(action) {
    const isEnable = (action === 'enable_all');
    const confirmed = confirm(
      isEnable
        ? "Are you sure you want to ENABLE all installed plugins?"
        : "Are you sure you want to DISABLE all plugins?\n(Note: skills-manager will remain enabled so you can continue managing your skills)"
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/bulk-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Bulk update failed");
      showToast(isEnable ? 'All plugins enabled!' : 'All plugins disabled (skills-manager active)');
      loadData();
    } catch (err) {
      showToast("Bulk toggle error: " + err.message, "error");
    }
  }

  async function openDoc(targetPath, title, baseDirHint = "") {
    const modal = document.getElementById("docModal");
    const titleEl = document.getElementById("modalDocTitle");
    const pathEl = document.getElementById("modalDocPath");
    const bodyEl = document.getElementById("modalDocBody");
    const backBtn = document.getElementById("modalBackBtn");

    titleEl.textContent = title;
    pathEl.textContent = targetPath;
    bodyEl.innerHTML = "<em>Loading document...</em>";
    modal.classList.add("open");

    if (DOC_HISTORY_STACK.length > 0) {
      backBtn.style.display = "inline-flex";
    } else {
      backBtn.style.display = "none";
    }

    try {
      let fetchUrl = `/api/doc?path=${encodeURIComponent(targetPath)}`;
      if (baseDirHint) {
        fetchUrl += `&baseDirHint=${encodeURIComponent(baseDirHint)}`;
      }
      const res = await fetch(fetchUrl);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not read document");

      CURRENT_MODAL_RAW = data.content || "";
      CURRENT_DOC_PATH = data.relativePath || targetPath;
      CURRENT_DOC_TITLE = title;
      CURRENT_DOC_DIR = data.relativeDir || "";

      pathEl.textContent = CURRENT_DOC_PATH;
      bodyEl.innerHTML = renderMarkdown(CURRENT_MODAL_RAW);
    } catch (err) {
      bodyEl.innerHTML = `<span style="color:#fb7185">Error reading document: ${escapeHtml(err.message)}</span>`;
    }
  }

  function handleDocLink(el) {
    const rawTarget = el.dataset.href;
    if (!rawTarget) return;

    if (rawTarget.startsWith("http://") || rawTarget.startsWith("https://")) {
      window.open(rawTarget, "_blank");
      return;
    }

    // Push current to history stack
    DOC_HISTORY_STACK.push({
      path: CURRENT_DOC_PATH,
      title: CURRENT_DOC_TITLE,
      dir: CURRENT_DOC_DIR
    });

    const displayTitle = rawTarget.split("/").pop().replace(".md", "").replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    openDoc(rawTarget, displayTitle, CURRENT_DOC_DIR);
  }

  function navigateDocBack() {
    if (DOC_HISTORY_STACK.length === 0) return;
    const prev = DOC_HISTORY_STACK.pop();
    openDoc(prev.path, prev.title, prev.dir);
  }

  function closeModal() {
    const modal = document.getElementById("docModal");
    modal.classList.remove("open");
    DOC_HISTORY_STACK.length = 0;
  }

  function closeModalOnBackdrop(e) {
    if (e.target.id === "docModal") closeModal();
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
      e.preventDefault();
      document.getElementById("searchInput").focus();
    }
  });

  async function copyModalContent() {
    if (!CURRENT_MODAL_RAW) return;
    await copyText(CURRENT_MODAL_RAW, "Copied document content to clipboard!");
  }

  async function copyText(text, successMsg) {
    try {
      await navigator.clipboard.writeText(text);
      showToast(successMsg || "Copied to clipboard!");
    } catch (err) {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast(successMsg || "Copied to clipboard!");
    }
  }

  function showToast(msg, type = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.className = `toast show ${type}`;
    setTimeout(() => {
      toast.classList.remove("show");
    }, 2400);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* Robust self-contained markdown renderer */
  function renderMarkdown(md) {
    if (!md) return "";

    // 1. Strip YAML frontmatter
    let text = md.replace(/^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]+/, "");

    // 2. Code blocks
    const codeBlocks = [];
    text = text.replace(/```([\w-]*)\r?\n([\s\S]*?)```/g, (match, lang, code) => {
      const id = `__CB_${codeBlocks.length}__`;
      codeBlocks.push({ lang, code });
      return id;
    });

    // 3. Tables
    const tables = [];
    text = text.replace(/(?:^\|.+?\|(?:\r?\n|$)){2,}/gm, (tableMatch) => {
      const lines = tableMatch.trim().split(/\r?\n/);
      if (lines.length >= 2) {
        let html = '<div class="table-wrap"><table>';
        lines.forEach((line, idx) => {
          if (line.match(/^\|\s*[-:]+\s*\|/)) return;
          const cells = line.split('|').slice(1, -1);
          const tag = (idx === 0) ? 'th' : 'td';
          html += '<tr>' + cells.map(c => `<${tag}>${escapeHtml(c.trim())}</${tag}>`).join('') + '</tr>';
        });
        html += '</table></div>';
        const id = `__TBL_${tables.length}__`;
        tables.push(html);
        return id;
      }
      return tableMatch;
    });

    // 4. Basic escape
    text = escapeHtml(text);

    // 5. Headers
    text = text.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

    // 6. Inline styles
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    text = text.replace(/^&gt; (.*?)$/gm, '<blockquote>$1</blockquote>');
    text = text.replace(/^---$/gm, '<hr style="border:none; border-top:1px solid rgba(255,255,255,0.08); margin:16px 0;"/>');

    // 7. Markdown links [text](target)
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, target) => {
      const t = target.trim();
      if (t.startsWith("http://") || t.startsWith("https://")) {
        return `<a href="${t}" target="_blank" rel="noopener noreferrer" class="ext-link">${label} ↗</a>`;
      } else {
        return `<a href="javascript:void(0)" class="doc-link" data-href="${t}" onclick="handleDocLink(this)">${label}</a>`;
      }
    });

    // 8. Grouped Unordered and Ordered Lists
    const rawLines = text.split(/\r?\n/);
    let inUl = false;
    let inOl = false;
    const listProcessed = [];
    rawLines.forEach(line => {
      const ulMatch = line.match(/^\s*[-*]\s+(.*)$/);
      const olMatch = line.match(/^\s*(\d+)\.\s+(.*)$/);
      if (ulMatch) {
        if (inOl) { listProcessed.push("</ol>"); inOl = false; }
        if (!inUl) { listProcessed.push("<ul>"); inUl = true; }
        listProcessed.push(`<li>${ulMatch[1]}</li>`);
      } else if (olMatch) {
        if (inUl) { listProcessed.push("</ul>"); inUl = false; }
        if (!inOl) { listProcessed.push("<ol>"); inOl = true; }
        listProcessed.push(`<li>${olMatch[2]}</li>`);
      } else {
        if (inUl) { listProcessed.push("</ul>"); inUl = false; }
        if (inOl) { listProcessed.push("</ol>"); inOl = false; }
        listProcessed.push(line);
      }
    });
    if (inUl) listProcessed.push("</ul>");
    if (inOl) listProcessed.push("</ol>");
    text = listProcessed.join("\n");

    // 9. Paragraphs
    text = text.split(/\r?\n\r?\n/).map(block => {
      const b = block.trim();
      if (!b) return "";
      if (b.startsWith('<h') || b.startsWith('<ul>') || b.startsWith('<ol>') || b.startsWith('<blockquote>') || b.startsWith('__CB_') || b.startsWith('__TBL_') || b.startsWith('<hr')) {
        return b;
      }
      return `<p>${b}</p>`;
    }).join('\n');

    // 10. Restore tables
    tables.forEach((tbl, idx) => {
      text = text.replace(`__TBL_${idx}__`, tbl);
    });

    // 11. Restore code blocks
    codeBlocks.forEach((cb, idx) => {
      const codeHtml = `<pre><code class="lang-${escapeHtml(cb.lang)}">${escapeHtml(cb.code.trim())}</code></pre>`;
      text = text.replace(`__CB_${idx}__`, codeHtml);
    });

    return text;
  }

  // Initial load
  loadData();
</script>
</body>
</html>
"""


class SkillsManagerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep terminal clean
        pass

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/preload.js":
            if PRELOAD_PATH.exists():
                self._send(200, "application/javascript; charset=utf-8", PRELOAD_PATH.read_bytes())
            else:
                self._send(200, "application/javascript; charset=utf-8", b"// Sidecar preload fallback\n")
            return

        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/plugins":
            data = scan_plugins_and_skills()
            self._send(200, "application/json; charset=utf-8", json.dumps(data).encode("utf-8"))
            return

        if path == "/api/health":
            self._send(200, "application/json; charset=utf-8", json.dumps({
                "status": "healthy",
                "service": "skills-manager",
                "port": PORT,
                "version": "1.0.0"
            }).encode("utf-8"))
            return

        if path == "/api/doc":
            qs = parse_qs(parsed.query)
            doc_path = qs.get("path", [""])[0]
            base_dir_hint = qs.get("baseDirHint", [""])[0]

            if not doc_path:
                self._send(400, "application/json; charset=utf-8", json.dumps({"error": "Missing path parameter"}).encode("utf-8"))
                return

            doc_info, err = read_document_content(doc_path, base_dir_hint)
            if err:
                self._send(403 if "Forbidden" in err else 404, "application/json; charset=utf-8", json.dumps({"error": err}).encode("utf-8"))
                return

            self._send(200, "application/json; charset=utf-8", json.dumps(doc_info).encode("utf-8"))
            return

        self._send(404, "text/plain; charset=utf-8", b"Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/api/toggle", "/api/bulk-toggle"):
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8", errors="replace"))
            except Exception:
                payload = {}

            if path == "/api/toggle":
                plugin_id = payload.get("pluginId", "").strip()
                enabled = bool(payload.get("enabled", True))
                if not plugin_id:
                    self._send(400, "application/json; charset=utf-8", json.dumps({"error": "Missing pluginId"}).encode("utf-8"))
                    return

                ok, msg = toggle_plugin_state(plugin_id, enabled)
                if not ok:
                    self._send(400 if "cannot be disabled" in msg else 500, "application/json; charset=utf-8", json.dumps({"error": msg}).encode("utf-8"))
                    return

                self._send(200, "application/json; charset=utf-8", json.dumps({
                    "success": True,
                    "pluginId": plugin_id,
                    "enabled": enabled,
                    "message": msg
                }).encode("utf-8"))
                return

            if path == "/api/bulk-toggle":
                action = payload.get("action", "enable_all")
                ok, msg = bulk_toggle_state(action)
                if not ok:
                    self._send(500, "application/json; charset=utf-8", json.dumps({"error": msg}).encode("utf-8"))
                    return

                self._send(200, "application/json; charset=utf-8", json.dumps({
                    "success": True,
                    "action": action,
                    "message": msg
                }).encode("utf-8"))
                return

        self._send(404, "text/plain; charset=utf-8", b"Not Found")


if __name__ == "__main__":
    server = ThreadingHTTPServer((BIND_HOST, PORT), SkillsManagerHandler)
    print(f"[skills-manager] listening on http://{BIND_HOST}:{PORT}", flush=True)
    server.serve_forever()
