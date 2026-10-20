"""Deploy integrated procurement assets to rel1-test.local and invalidate Frappe's page cache."""
import hashlib
import json
import subprocess
from pathlib import Path
from datetime import datetime
import frappe
BENCH = Path("/home/bitssecureit/rel1-bench")
PAGE = BENCH / "apps/bsgroup/bsgroup/bs_group/page/bs_procurement"
allowed = {"__init__.py", "bs_procurement.js", "bs_procurement.css", "bs_procurement.json", "bs_procurement.py", "__pycache__"}
unexpected = {p.name for p in PAGE.iterdir()} - allowed
if unexpected:
    raise SystemExit("Unexpected page assets: " + ", ".join(sorted(unexpected)))
subprocess.run(["node", "--check", str(PAGE / "bs_procurement.js")], check=True)
path = PAGE / "bs_procurement.json"
doc = json.loads(path.read_text())
doc["modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
path.write_text(json.dumps(doc, indent=2) + "\n")
frappe.init(site="rel1-test.local",sites_path=str(BENCH / "sites"))
frappe.connect();frappe.set_user("Administrator")
try:
    frappe.reload_doc("bs_group", "page", "bs_procurement", force=True)
    # boot.page_info.modified invalidates _page:bs-procurement in Desk sync_pages().
    frappe.db.set_value("Page", "bs-procurement", "modified", doc["modified"], update_modified=False)
    frappe.db.commit()
    frappe.clear_cache()
    from frappe.desk.desk_page import get
    served = get("bs-procurement")
    script = served.script
    subprocess.run(["node", "--check", "-"], input=script, text=True, check=True)
    assert '20261020-standard-2' in script
    assert 'QA_REPORT' not in script
    print(json.dumps({"site":frappe.local.site,"page_modified":str(frappe.db.get_value("Page","bs-procurement","modified")),
        "build":"20261020-standard-2","script_sha256":hashlib.sha256(script.encode()).hexdigest(),
        "disk_js_sha256":hashlib.sha256((PAGE/"bs_procurement.js").read_bytes()).hexdigest(),
        "runtime_files":sorted(p.name for p in PAGE.iterdir())},indent=2))
finally:
    frappe.destroy()
