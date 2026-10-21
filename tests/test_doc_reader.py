import urllib.parse
from pathlib import Path

PLUGINS_DIR = Path(r"C:\Users\medta\.gemini\config\plugins")

def read_document_content(rel_or_abs_path: str, base_dir_hint: str = ""):
    raw = rel_or_abs_path.strip()
    if raw.startswith("file:///"):
        raw = raw[8:]
    elif raw.startswith("file://"):
        raw = raw[7:]

    # Decode any URL encoded characters (e.g. %20)
    raw = urllib.parse.unquote(raw)

    p = Path(raw)
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

    # Security check: must reside inside PLUGINS_DIR
    plugins_resolved = PLUGINS_DIR.resolve()
    try:
        p.relative_to(plugins_resolved)
    except ValueError:
        return None, "Forbidden: Path is outside plugins directory"

    if not p.is_file():
        return None, "File not found"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return {
            "name": p.name,
            "path": str(p),
            "relativePath": str(p.relative_to(plugins_resolved)).replace("\\", "/"),
            "sizeBytes": p.stat().st_size,
            "content": content,
        }, None
    except Exception as e:
        return None, str(e)

if __name__ == "__main__":
    t1, err = read_document_content("skills-manager/skills/skills-manager/SKILL.md")
    assert err is None and t1["name"] == "SKILL.md", f"T1 failed: {err}"
    print("T1 Passed: SKILL.md read")

    t2, err = read_document_content("file:///C:/Users/medta/.gemini/config/plugins/cybersecurity-suite/skills/pentest/references/linux-pentesting.md")
    assert err is None and t2["name"] == "linux-pentesting.md", f"T2 failed: {err}"
    print("T2 Passed: file:/// URI handled")

    # Relative resolution from base hint
    t3, err = read_document_content("linux-pentesting.md", base_dir_hint="cybersecurity-suite/skills/pentest/references")
    assert err is None and t3["name"] == "linux-pentesting.md", f"T3 failed: {err}"
    print("T3 Passed: relative resolution with base_dir_hint handled")

    t4, err = read_document_content("../../config.json")
    assert err and "Forbidden" in err, f"T4 failed: expected Forbidden, got {err}"
    print("T4 Passed: traversal caught")

    t5, err = read_document_content("nonexistent.md")
    assert err and "File not found" in err, f"T5 failed: {err}"
    print("T5 Passed: 404 handled")

    print("\nAll doc reader tests passed!")
