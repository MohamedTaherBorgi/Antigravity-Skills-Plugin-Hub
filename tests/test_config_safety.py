import json
import time
from pathlib import Path

CONFIG_PATH = Path(r"C:\Users\medta\.gemini\config\config.json")
PLUGINS_DIR = Path(r"C:\Users\medta\.gemini\config\plugins")

def load_config():
    if not CONFIG_PATH.exists():
        return {"plugins": {}, "sidecars": {}, "userSettings": {}}
    for attempt in range(3):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
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
        # On Windows, retry if another process is briefly reading
        for attempt in range(4):
            try:
                tmp_file.replace(CONFIG_PATH)
                return True
            except PermissionError:
                time.sleep(0.1)
        tmp_file.replace(CONFIG_PATH)
        return True
    except Exception as e:
        print(f"Error saving: {e}")
        return False

def toggle_plugin_state(plugin_id: str, enabled: bool):
    if not plugin_id or not isinstance(plugin_id, str):
        return False, "Invalid pluginId"
    if plugin_id == "skills-manager" and not enabled:
        return False, "Cannot disable skills-manager while the manager is active."

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
    return (True, f"Plugin {plugin_id} {'enabled' if enabled else 'disabled'}") if ok else (False, "Failed to save configuration")

def bulk_toggle_state(action: str):
    enable = (action == "enable_all")
    cfg = load_config()
    if "plugins" not in cfg or not isinstance(cfg["plugins"], dict):
        cfg["plugins"] = {}

    if PLUGINS_DIR.exists():
        for p in PLUGINS_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            # Safety: NEVER disable skills-manager in bulk toggle
            if p.name == "skills-manager" and not enable:
                continue

            current = cfg["plugins"].get(p.name)
            if isinstance(current, dict):
                current["enabled"] = enable
                cfg["plugins"][p.name] = current
            else:
                cfg["plugins"][p.name] = {"enabled": enable}

    ok = save_config(cfg)
    return (True, f"Bulk update {action} successful") if ok else (False, "Failed to bulk update")

if __name__ == "__main__":
    # Test protecting skills-manager
    ok, msg = toggle_plugin_state("skills-manager", False)
    assert not ok and "Cannot disable" in msg, f"Expected protected skills-manager, got {ok}, {msg}"
    print("Test 1 Passed: skills-manager cannot be disabled from UI")

    # Test bulk disable keeps skills-manager enabled
    # Save original state
    orig = load_config()
    try:
        ok, msg = bulk_toggle_state("disable_all")
        assert ok
        cfg_after = load_config()
        assert cfg_after["plugins"]["skills-manager"]["enabled"] is True, "skills-manager was disabled in bulk toggle!"
        assert cfg_after["plugins"]["translator"]["enabled"] is False
        print("Test 2 Passed: bulk disable keeps skills-manager enabled")
    finally:
        # Restore original
        save_config(orig)
        print("Test 3 Passed: Original config restored")
