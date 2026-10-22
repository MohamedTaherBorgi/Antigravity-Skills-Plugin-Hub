import re
import json
from pathlib import Path

PLUGINS_DIR = Path(r"C:\Users\medta\.gemini\config\plugins")

def test_parse():
    for p in sorted(PLUGINS_DIR.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        skills_dir = p / "skills"
        if not skills_dir.is_dir():
            continue
        for s in skills_dir.iterdir():
            sm = s / "SKILL.md"
            if not sm.is_file():
                continue
            content = sm.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
            fm_raw, body_text = fm_match.groups() if fm_match else ("", content)

            fm_name = s.name
            for line in fm_raw.splitlines():
                if line.startswith("name:"):
                    fm_name = line.split("name:", 1)[1].strip()
                    break

            desc_m = re.search(r"description:\s*(?:>-|>|\|-|\||\"|')?\s*(.*?)(?=\n[a-z0-9_-]+:|\Z)", fm_raw, re.DOTALL)
            fm_desc = " ".join(desc_m.group(1).strip().split()) if desc_m else ""
            fm_desc = fm_desc.strip('"\'')

            # Slash commands
            detected_commands = []
            for m in re.finditer(r'["\'](/[\w-]+)["\']', fm_desc):
                c = m.group(1)
                if not c.startswith(('/usr', '/etc', '/bin', '/var', '/tmp', '/dev')):
                    if c not in detected_commands:
                        detected_commands.append(c)

            # Check title or slash sections
            for m in re.finditer(r'(?:Quick Slash Command|Slash Command|Trigger on|Quick Command)[s]?:\s*(/[\w-]+)', body_text, re.IGNORECASE):
                c = m.group(1)
                if c not in detected_commands:
                    detected_commands.append(c)

            KNOWN = {
                "pentest": ["/pentest"],
                "superpowers": ["/superpowers"],
                "ui-design": ["/ui-design"],
                "documents": ["/documents"],
                "exam-prep": ["/exam-prep"],
                "prompt-optimizer": ["/prompt-optimizer"],
                "usage-stats": ["/usage-stats"],
                "skills-manager": ["/skills", "/skills-manager"],
                "creative-motion": ["/motion", "/creative-motion"]
            }
            if fm_name in KNOWN:
                for c in KNOWN[fm_name]:
                    if c not in detected_commands:
                        detected_commands.append(c)

            has_slash = len(detected_commands) > 0
            has_auto = any(k in fm_desc.lower() for k in ["trigger", "whenever", "intent", "use when", "activate", "mentions of"])

            if has_slash and has_auto:
                tt = "Hybrid (Slash & Auto)"
            elif has_slash:
                tt = "Slash Command"
            else:
                tt = "Auto-Activated"

            print(f"{fm_name:24} | {tt:22} | {detected_commands}")

if __name__ == "__main__":
    test_parse()
