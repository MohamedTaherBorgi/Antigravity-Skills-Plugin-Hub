import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

TEST_PORT = 18799
os.environ["ANTIGRAVITY_SIDECAR_WEB_PORT"] = str(TEST_PORT)

server_script = Path(r"C:\Users\medta\.gemini\config\plugins\skills-manager\sidecars\skills-manager\server.py")
config_path = Path(r"C:\Users\medta\.gemini\config\config.json")

print("[TEST] Launching server process on port", TEST_PORT)
proc = subprocess.Popen(["python", str(server_script)], env=os.environ)

time.sleep(1.5)

try:
    base_url = f"http://127.0.0.1:{TEST_PORT}"

    # Test 1: Health check
    print("\n--- Test 1: Health Check ---")
    req = urllib.request.urlopen(f"{base_url}/api/health", timeout=3)
    assert req.status == 200
    health_data = json.loads(req.read().decode())
    print("Health response:", health_data)
    assert health_data["status"] == "healthy"
    assert health_data["port"] == TEST_PORT

    # Test 2: Preload JS
    print("\n--- Test 2: Preload.js ---")
    req = urllib.request.urlopen(f"{base_url}/preload.js", timeout=3)
    assert req.status == 200
    js_content = req.read().decode()
    print("Preload length:", len(js_content))
    assert len(js_content) > 0

    # Test 3: Index HTML UI
    print("\n--- Test 3: Index HTML UI ---")
    req = urllib.request.urlopen(f"{base_url}/", timeout=3)
    assert req.status == 200
    html_content = req.read().decode()
    print("HTML length:", len(html_content))
    assert "Skills & Plugin Hub" in html_content
    assert "statTotalPlugins" in html_content
    assert "docModal" in html_content
    assert "data-copy=" in html_content  # Verifies safe attribute encoding
    assert "handleDocLink" in html_content  # Verifies markdown doc link handler
    assert "scripts-drawer" in html_content  # Verifies script inspection

    # Test 4: GET /api/plugins
    print("\n--- Test 4: GET /api/plugins ---")
    req = urllib.request.urlopen(f"{base_url}/api/plugins", timeout=3)
    assert req.status == 200
    plugins_data = json.loads(req.read().decode())
    plugins = plugins_data["plugins"]
    stats = plugins_data["stats"]
    print(f"Total plugins scanned: {len(plugins)}")
    assert len(plugins) == 13

    # Check creative-motion plugin and skill properties
    cm_plugin = next(p for p in plugins if p["id"] == "creative-motion")
    assert cm_plugin["skillsCount"] == 1
    assert cm_plugin["title"] == "Creative Motion & Shaders Suite"
    cm_skill = cm_plugin["skills"][0]
    assert cm_skill["name"] == "creative-motion"
    assert cm_skill["referencesCount"] == 3
    assert "/motion" in cm_skill["commandTriggers"]
    assert "/creative-motion" in cm_skill["commandTriggers"]
    assert "Hybrid" in cm_skill["triggerType"]
    print("Verified creative-motion metadata, 3 reference guides, and slash commands.")

    # Check skills-manager host properties
    sm_plugin = next(p for p in plugins if p["id"] == "skills-manager")
    assert sm_plugin["isHost"] is True
    assert sm_plugin["skillsCount"] == 1
    sm_skill = sm_plugin["skills"][0]
    assert sm_skill["name"] == "skills-manager"
    assert "/skills" in sm_skill["commandTriggers"]
    assert "/skills-manager" in sm_skill["commandTriggers"]
    assert "Hybrid" in sm_skill["triggerType"]
    print("Verified skills-manager has both /skills and /skills-manager and is marked isHost.")

    # Check auto-activated skill classification (no false slash commands)
    chrome_ext_plugin = next(p for p in plugins if p["id"] == "modern-web-guidance-plugin")
    chrome_skill = next(s for s in chrome_ext_plugin["skills"] if s["name"] == "chrome-extensions")
    assert chrome_skill["triggerType"] == "Auto-Activated"
    assert chrome_skill["commandTriggers"] == []
    print("Verified auto-activated skills (chrome-extensions) have no fake slash commands.")

    gemini_api_plugin = next(p for p in plugins if p["id"] == "gemini-api")
    gemini_skill = next(s for s in gemini_api_plugin["skills"] if s["name"] == "gemini-api-dev")
    assert gemini_skill["triggerType"] == "Auto-Activated"
    assert gemini_skill["commandTriggers"] == []
    print("Verified gemini-api-dev is correctly classified as Auto-Activated.")

    # Check sidecar metadata extraction
    translator_plugin = next(p for p in plugins if p["id"] == "translator")
    assert translator_plugin["hasSidecar"] is True
    assert len(translator_plugin["sidecars"]) >= 1
    assert translator_plugin["sidecars"][0]["name"] == "translator"
    print("Verified sidecar metadata extraction for translator.")

    # Test 5: GET /api/doc
    print("\n--- Test 5: GET /api/doc ---")
    # 5a: Standard relative path
    doc_req = urllib.request.urlopen(f"{base_url}/api/doc?path=skills-manager/skills/skills-manager/SKILL.md", timeout=3)
    assert doc_req.status == 200
    doc_res = json.loads(doc_req.read().decode())
    assert "Skills & Plugin Hub" in doc_res["content"]
    assert doc_res["relativePath"] == "skills-manager/skills/skills-manager/SKILL.md"
    print("5a Passed: Standard relative path read.")

    # 5b: file:/// URI
    file_uri = "file:///C:/Users/medta/.gemini/config/plugins/cybersecurity-suite/skills/pentest/references/linux-pentesting.md"
    doc_req2 = urllib.request.urlopen(f"{base_url}/api/doc?path={file_uri}", timeout=3)
    assert doc_req2.status == 200
    doc_res2 = json.loads(doc_req2.read().decode())
    assert doc_res2["name"] == "linux-pentesting.md"
    print("5b Passed: file:/// URI handled.")

    # 5c: Relative link resolution with baseDirHint
    doc_req3 = urllib.request.urlopen(f"{base_url}/api/doc?path=windows-ad-pentesting.md&baseDirHint=cybersecurity-suite/skills/pentest/references", timeout=3)
    assert doc_req3.status == 200
    doc_res3 = json.loads(doc_req3.read().decode())
    assert doc_res3["name"] == "windows-ad-pentesting.md"
    print("5c Passed: Relative path with baseDirHint handled.")

    # 5d: Verify creative-motion reference guide reading
    doc_req4 = urllib.request.urlopen(f"{base_url}/api/doc?path=creative-motion/skills/creative-motion/references/micro-interactions.md", timeout=3)
    assert doc_req4.status == 200
    doc_res4 = json.loads(doc_req4.read().decode())
    assert "Emil Kowalski" in doc_res4["content"]
    assert doc_res4["name"] == "micro-interactions.md"
    print("5d Passed: creative-motion reference guide read.")

    # Test 6: Security - Directory Traversal Prevention
    print("\n--- Test 6: Security - Path Traversal Check ---")
    try:
        urllib.request.urlopen(f"{base_url}/api/doc?path=../../config.json", timeout=3)
        assert False, "Path traversal should have failed!"
    except urllib.error.HTTPError as e:
        assert e.code == 403
        print(f"Correctly caught HTTP 403 for traversal attempt: {e.read().decode()}")

    # Test 7: Safety - Prevent Disabling skills-manager
    print("\n--- Test 7: Safety - Prevent Disabling Host Manager ---")
    try:
        post_data = json.dumps({"pluginId": "skills-manager", "enabled": False}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/toggle", data=post_data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
        assert False, "Disabling skills-manager should be rejected!"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        res = json.loads(e.read().decode())
        assert "cannot be disabled" in res["error"]
        print(f"Correctly rejected disabling skills-manager: {res['error']}")

    # Test 8: POST /api/toggle for other plugins
    print("\n--- Test 8: POST /api/toggle ---")
    post_data = json.dumps({"pluginId": "translator", "enabled": False}).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/api/toggle", data=post_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode())
        assert res["success"] is True
        assert res["enabled"] is False

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg["plugins"]["translator"]["enabled"] is False
    print("Verified: config.json translator.enabled is False on disk.")

    # Toggle back ON
    post_data_on = json.dumps({"pluginId": "translator", "enabled": True}).encode("utf-8")
    req_on = urllib.request.Request(f"{base_url}/api/toggle", data=post_data_on, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req_on, timeout=3) as resp:
        assert resp.status == 200
        res_on = json.loads(resp.read().decode())
        assert res_on["success"] is True
        assert res_on["enabled"] is True

    cfg_after = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg_after["plugins"]["translator"]["enabled"] is True
    print("Verified: config.json translator.enabled is True on disk.")

    # Test 9: POST /api/bulk-toggle Safety
    print("\n--- Test 9: POST /api/bulk-toggle Safety ---")
    orig_config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        bulk_data = json.dumps({"action": "disable_all"}).encode("utf-8")
        bulk_req = urllib.request.Request(f"{base_url}/api/bulk-toggle", data=bulk_data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(bulk_req, timeout=3) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode())
            assert res["success"] is True

        bulk_cfg = json.loads(config_path.read_text(encoding="utf-8"))
        # skills-manager MUST remain enabled!
        assert bulk_cfg["plugins"]["skills-manager"]["enabled"] is True, "CRITICAL: skills-manager was disabled in bulk toggle!"
        # Other plugins should be disabled
        assert bulk_cfg["plugins"]["translator"]["enabled"] is False
        assert bulk_cfg["plugins"]["superpowers"]["enabled"] is False
        print("Verified: bulk disable safely preserves skills-manager enabled.")
    finally:
        # Restore original config
        config_path.write_text(json.dumps(orig_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Restored original config.json after bulk test.")

    print("\n=========================================")
    print("ALL 9 TEST SUITES COMPLETED AND VERIFIED!")
    print("=========================================")

finally:
    print("[TEST] Terminating server process...")
    proc.terminate()
    proc.wait()
