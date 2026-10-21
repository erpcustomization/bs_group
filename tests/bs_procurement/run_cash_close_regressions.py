"""Run the existing purchasing/accounting regressions sequentially on the test site."""
import json
import re
import subprocess
import sys
from pathlib import Path

BENCH = Path("/home/bitssecureit/rel1-bench")
ROOT = BENCH / "apps/bsgroup"
TESTS = ROOT / "tests/bs_procurement"
checks = {}
for suite in ("payment_policy", "standard_documents", "mohan_approval", "pr_supporting",
              "accounts_continuity", "sales_handover", "qc_gaps", "deployment", "selected_print_format"):
    log = ROOT / "qa_reports" / f"cash_close_{suite}.log"
    with log.open("w") as output:
        result = subprocess.run([sys.executable, str(TESTS / f"test_{suite}.py")],
                                cwd=BENCH / "sites", stdout=output, stderr=subprocess.STDOUT)
    contents = log.read_text()
    matches = re.findall(r'"passed":\s*(\d+)', contents)
    if result.returncode or "Traceback (most recent call last)" in contents or not matches:
        print(f"FAILED {suite}; see {log}", flush=True)
        raise SystemExit(1)
    checks[suite] = int(matches[-1])
    print(f"PASS {suite}: {checks[suite]} checks", flush=True)
print(json.dumps(dict(checks=checks, passed=sum(checks.values())), indent=2), flush=True)
