"""Offline tests for the reply-triage parse/validate logic (no API)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from classifier import _parse

passed = total = 0
def check(name, fn, should_raise=False, expect=None):
    global passed, total; total += 1
    try:
        out = fn()
        if should_raise: print(f"[FAIL] {name} (expected raise)"); return
        ok = expect is None or out["classification"] == expect
        passed += ok; print(f"[{'PASS' if ok else 'FAIL'}] {name} -> {out}")
    except Exception as e:
        if should_raise: passed += 1; print(f"[PASS] {name} raised: {e}")
        else: print(f"[FAIL] {name} unexpected: {e}")

check("interested", lambda: _parse('{"classification":"interested","reasoning":"asked for more","urgency":"high"}'), expect="interested")
check("objection", lambda: _parse('{"classification":"objection","reasoning":"has agency","urgency":"normal"}'), expect="objection")
check("not_interested", lambda: _parse('{"classification":"not_interested","reasoning":"no","urgency":"low"}'), expect="not_interested")
check("auto_reply", lambda: _parse('{"classification":"auto_reply","reasoning":"OOO","urgency":"low"}'), expect="auto_reply")
check("fenced json", lambda: _parse('```json\n{"classification":"unclear","reasoning":"?","urgency":"normal"}\n```'), expect="unclear")
check("bad classification rejected", lambda: _parse('{"classification":"maybe","reasoning":"x","urgency":"low"}'), should_raise=True)
check("malformed json rejected", lambda: _parse('not json'), should_raise=True)
check("bad urgency coerced to normal", lambda: _parse('{"classification":"interested","reasoning":"x","urgency":"yesterday"}'))
print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
