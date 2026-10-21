"""URL-organized, deterministic API regression tests. Paid LLMs are mocked."""
import argparse
from datetime import datetime
import html
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReportResult(unittest.TextTestResult):
    records = None
    def startTestRun(self):
        super().startTestRun()
        self.records = []
    def addSuccess(self, test):
        super().addSuccess(test); self.records.append((str(test), "PASS", ""))
    def addFailure(self, test, err):
        super().addFailure(test, err); self.records.append((str(test), "FAIL", self._exc_info_to_string(err, test)))
    def addError(self, test, err):
        super().addError(test, err); self.records.append((str(test), "FAIL", self._exc_info_to_string(err, test)))
    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.records.append((str(test), "NOT RUN", reason))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Only cases whose URL directory contains this text")
    args = parser.parse_args()
    suite = unittest.TestSuite()
    for index, path in enumerate(sorted((ROOT / "apitest/cases").rglob("case.py"))):
        if args.url and args.url not in path.as_posix():
            continue
        spec = importlib.util.spec_from_file_location(f"api_case_{index}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(module.suite() if hasattr(module, "suite") else unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=2, resultclass=ReportResult).run(suite)
    report = ROOT / "apitest/report"
    report.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"<tr><td>{html.escape(name)}</td><td>{status}</td><td><pre>{html.escape(detail)}</pre></td></tr>" for name, status, detail in result.records)
    document = f'''<!doctype html><meta charset="utf-8"><title>CampusClaw API report</title>
    <style>body{{font:15px system-ui;max-width:1300px;margin:40px auto;color:#243544}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #dde5ec;padding:10px;text-align:left}}pre{{white-space:pre-wrap;font-size:12px}}th{{background:#eef6f5}}</style>
    <h1>第5课 API 回归报告</h1><p>{datetime.now().isoformat(timespec='seconds')} | SQL fixture: SQLite | Qdrant: test double | DeepSeek: mock</p>
    <p>执行 {result.testsRun} 项；失败 {len(result.failures)+len(result.errors)} 项；跳过 {len(result.skipped)} 项。真实服务测试由独立 live 脚本执行。</p>
    <table><tr><th>用例</th><th>结果</th><th>详情</th></tr>{rows}</table>'''
    (report / "index.html").write_text(document, encoding="utf-8")
    (report / "summary.json").write_text(json.dumps({"tests": result.testsRun, "failures": len(result.failures)+len(result.errors), "skipped": len(result.skipped)}, indent=2), encoding="utf-8")
    print("HTML report:", report / "index.html")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
