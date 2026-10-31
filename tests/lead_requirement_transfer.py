"""Ensure website enquiries carry into conversion without replacing edited requirements."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

class Lead(dict):
    name = "LEAD-TEST"
    def is_new(self):
        return False

class RequirementTests(unittest.TestCase):
    def resolve(self, requirement, rows):
        calls = []
        def get_all(doctype, **kwargs):
            calls.append((doctype, kwargs))
            return rows
        source = Path(__file__).resolve().parents[1] / "bsgroup/lead_lifecycle.py"
        tree = ast.parse(source.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "customer_requirement")
        env = {"frappe": SimpleNamespace(get_all=get_all)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), env)
        return env["customer_requirement"](Lead(custom_requirement=requirement)), calls

    def test_saved_requirement_wins(self):
        result, calls = self.resolve("Updated scope", [{"transcript":"Original enquiry"}])
        self.assertEqual(result, "Updated scope")
        self.assertEqual(calls, [])

    def test_website_requirement_used_for_existing_lead(self):
        result, calls = self.resolve("", [{"transcript":"Customer website requirement"}])
        self.assertEqual(result, "Customer website requirement")
        self.assertEqual(calls[0][1]["filters"], {"converted_lead":"LEAD-TEST"})

    def test_missing_requirement_remains_empty(self):
        self.assertEqual(self.resolve(None, [])[0], "")
        self.assertEqual(self.resolve(" ", [{"transcript":None}])[0], "")

if __name__ == "__main__":
    unittest.main()
