import sys
from pathlib import Path

# Add sidecars/skills-manager to sys.path so we test actual production code
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str((REPO_ROOT / "sidecars" / "skills-manager").resolve()))

from server import read_document_content, PLUGINS_DIR


def test_doc_reader():
    print("--- Running test_doc_reader against server.py ---")

    # T1: Standard relative path
    t1, err = read_document_content("skills-manager/skills/skills-manager/SKILL.md")
    assert err is None and t1["name"] == "SKILL.md", f"T1 failed: {err}"
    assert "Skills & Plugin Hub" in t1["content"]
    assert t1["relativeDir"] == "skills-manager/skills/skills-manager"
    print("T1 Passed: SKILL.md read")

    # T2: file:/// URI
    t2, err = read_document_content("file:///C:/Users/medta/.gemini/config/plugins/cybersecurity-suite/skills/pentest/references/linux-pentesting.md")
    assert err is None and t2["name"] == "linux-pentesting.md", f"T2 failed: {err}"
    print("T2 Passed: file:/// URI handled")

    # T3: Relative resolution from baseDirHint
    t3, err = read_document_content("linux-pentesting.md", base_dir_hint="cybersecurity-suite/skills/pentest/references")
    assert err is None and t3["name"] == "linux-pentesting.md", f"T3 failed: {err}"
    print("T3 Passed: relative resolution with base_dir_hint handled")

    # T4: creative-motion SKILL.md
    t4, err = read_document_content("creative-motion/skills/creative-motion/SKILL.md")
    assert err is None and t4["name"] == "SKILL.md", f"T4 failed: {err}"
    assert "Creative Motion & Shaders Suite" in t4["content"]
    print("T4 Passed: creative-motion SKILL.md read")

    # T5: creative-motion reference guides (all 3)
    cm_refs = ["micro-interactions.md", "gsap-cinematic-scroll.md", "shaders-and-backgrounds.md"]
    for ref in cm_refs:
        res, err = read_document_content(f"creative-motion/skills/creative-motion/references/{ref}")
        assert err is None, f"Failed reading {ref}: {err}"
        assert res["name"] == ref
        assert res["sizeBytes"] > 1000
        assert len(res["content"]) > 1000

        # Also test with baseDirHint
        hint_res, hint_err = read_document_content(ref, base_dir_hint="creative-motion/skills/creative-motion/references")
        assert hint_err is None, f"Failed reading {ref} via baseDirHint: {hint_err}"
        assert hint_res["name"] == ref
    print("T5 Passed: All 3 creative-motion reference guides read directly and via baseDirHint")

    # T6: Security path traversal protection
    t6, err = read_document_content("../../config.json")
    assert err and "Forbidden" in err, f"T6 failed: expected Forbidden, got {err}"
    print("T6 Passed: traversal caught")

    # T7: 404 nonexistent file
    t7, err = read_document_content("nonexistent.md")
    assert err and "File not found" in err, f"T7 failed: {err}"
    print("T7 Passed: 404 handled")

    print("\nAll doc reader tests passed!")


if __name__ == "__main__":
    test_doc_reader()
