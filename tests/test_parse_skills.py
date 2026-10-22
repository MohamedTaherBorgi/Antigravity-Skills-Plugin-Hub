import sys
from pathlib import Path

# Add sidecars/skills-manager to sys.path so we test actual production code
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str((REPO_ROOT / "sidecars" / "skills-manager").resolve()))

from server import parse_skill_file, scan_plugins_and_skills, PLUGINS_DIR


def test_parse_skills():
    print("--- Running test_parse_skills against server.py ---")
    data = scan_plugins_and_skills()
    plugins = data["plugins"]
    stats = data["stats"]

    assert len(plugins) == 13, f"Expected 13 plugins, found {len(plugins)}"
    assert stats["totalPlugins"] == 13
    assert stats["totalSkills"] == 15

    # Map skills by name
    all_skills = {}
    for p in plugins:
        for s in p["skills"]:
            all_skills[s["name"]] = s

    # 1. Assert creative-motion
    assert "creative-motion" in all_skills, "creative-motion skill missing!"
    cm = all_skills["creative-motion"]
    assert cm["name"] == "creative-motion"
    assert "/motion" in cm["commandTriggers"], f"Expected /motion in {cm['commandTriggers']}"
    assert "/creative-motion" in cm["commandTriggers"], f"Expected /creative-motion in {cm['commandTriggers']}"
    assert cm["triggerType"] == "Hybrid (Slash & Auto)", f"Expected Hybrid, got {cm['triggerType']}"
    assert cm["referencesCount"] == 3, f"Expected 3 references, got {cm['referencesCount']}"
    ref_names = [r["name"] for r in cm["references"]]
    assert "micro-interactions.md" in ref_names
    assert "gsap-cinematic-scroll.md" in ref_names
    assert "shaders-and-backgrounds.md" in ref_names
    print("[OK] creative-motion parsed accurately with /motion, /creative-motion and 3 references")

    # 2. Assert skills-manager
    sm = all_skills["skills-manager"]
    assert "/skills" in sm["commandTriggers"]
    assert "/skills-manager" in sm["commandTriggers"]
    assert sm["triggerType"] == "Hybrid (Slash & Auto)"
    print("[OK] skills-manager parsed accurately")

    # 3. Assert superpowers & pentest
    sp = all_skills["superpowers"]
    assert "/superpowers" in sp["commandTriggers"]
    pt = all_skills["pentest"]
    assert "/pentest" in pt["commandTriggers"]
    print("[OK] superpowers and pentest parsed accurately")

    # 4. Assert chrome-extensions (Auto-Activated)
    ce = all_skills["chrome-extensions"]
    assert ce["commandTriggers"] == []
    assert ce["triggerType"] == "Auto-Activated"
    print("[OK] chrome-extensions correctly classified as Auto-Activated")

    # 5. Check schema integrity across all 15 skills
    required_keys = {
        "name", "displayName", "description", "slashCommand",
        "commandTriggers", "triggerType", "referencesCount",
        "references", "scriptsCount", "scripts", "path",
        "relativePath", "skillMdRelative"
    }
    for name, s in all_skills.items():
        missing = required_keys - set(s.keys())
        assert not missing, f"Skill {name} missing keys: {missing}"
        assert s["name"] and s["displayName"] and s["description"], f"Skill {name} has empty fields"
        print(f"  - {s['name']:24} | {s['triggerType']:22} | {s['commandTriggers']}")

    print("\nAll skill parser assertions passed!")


if __name__ == "__main__":
    test_parse_skills()
