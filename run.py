"""One command for the whole Duelist Ledger v0 run (contract v0.1).

In plain words:
  py -3.14 run.py                         runs the unit tests, then every scenario in
                                          scenarios/v0.1/ (else scenarios/, else the smoke
                                          fixtures in tests/fixtures), and writes out/report.md.
  py -3.14 run.py --scenarios <dir>       same, on another scenario folder.
  py -3.14 run.py --scenarios <dir> --reveal <expectations.json> --salt <salt.txt>
                                          first checks the seal (default
                                          sealed/v0.1/expectations.seal.json, or --seal <path>);
                                          stops at once if it does not match; otherwise also
                                          compares every sealed expectation and lists mismatches.
  py -3.14 run.py --subprocess            also runs one demo session over a real stdio pipe.

Relative paths are taken from the current folder, or from this build's folder if they are not
found there. Per-run working files go in short folders under the system temp directory; only
summaries go in out/. Exit code is non-zero only if unit tests fail, an invariant breaks in a
strict mode, or the seal does not verify. Expectation mismatches are findings, not failures.
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from duelist_ledger import CAVEAT, CONTRACT, CONTRACT_DIR  # noqa: E402
from duelist_ledger.harness import (STRICT_INVARIANT_MODES, compare, load_scenarios, modes_for,  # noqa: E402
                                    run_one, variant_count)
from duelist_ledger.metrics import compute  # noqa: E402
from duelist_ledger.policy import load_config  # noqa: E402
from duelist_ledger import report  # noqa: E402
from duelist_ledger.seal import check_reveal_files  # noqa: E402


def run_unit_tests():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    return {"ok": result.wasSuccessful(), "run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": False, "output_tail": stream.getvalue()[-4000:]}


def pipe_driver(gw, spec):
    """Play one session with the agent in a child process, over stdin/stdout JSON lines."""
    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--agent-child"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            encoding="utf-8", env=env)
    proc.stdin.write(json.dumps(spec) + "\n")
    proc.stdin.flush()
    finished = False
    count = 0
    while count < 2000:
        line = proc.stdout.readline()
        if not line:
            break
        count += 1
        msg = json.loads(line)
        reply = gw.handle(msg)
        if isinstance(msg, dict) and msg.get("op") == "finish":
            finished = True
        try:
            proc.stdin.write(json.dumps(reply) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            break
    try:
        proc.stdin.close()
    except OSError:
        pass
    proc.wait(timeout=60)
    proc.stdout.close()
    gw.end_session(finished)
    return finished


def subprocess_demo(scenarios, policy, sinks, tmp_root):
    if not scenarios:
        return {"ok": False, "why": "no scenario to demo"}
    sc = scenarios[0]
    piped = run_one(sc, "V2", 0, os.path.join(tmp_root, "pipe"), policy, sinks, driver=pipe_driver)
    local = run_one(sc, "V2", 0, os.path.join(tmp_root, "local"), policy, sinks)
    keys = ("outcomes", "holds", "trips", "goal_met", "adversary_success", "counters")
    same = all(piped["summary"][k] == local["summary"][k] for k in keys)
    return {"ok": same and piped["replay"]["total"] == piped["replay"]["matched"],
            "scenario": sc.get("id"), "outcomes": piped["summary"]["outcomes"],
            "matches_in_process": same}


def resolve_path(path):
    """A relative path is taken from the current folder, else from this build's folder."""
    if not path or os.path.isabs(path) or os.path.exists(path):
        return path
    return os.path.join(ROOT, path)


def default_scenario_dir():
    for cand in (os.path.join(ROOT, "scenarios", CONTRACT_DIR), os.path.join(ROOT, "scenarios")):
        if load_scenarios(cand):
            return cand
    return os.path.join(ROOT, "tests", "fixtures")


def expectation_diff(expectations, scenarios, results, load_errors=()):
    mismatches, compared, matched = [], 0, 0
    ids = {str(sc.get("id")) for sc in scenarios}
    rejected = {str(e["scenario"]): e["error"] for e in load_errors}
    for sid, modes in sorted((expectations.get("scenarios") or {}).items()):
        if str(sid) not in ids:
            actual = "load error: %s" % rejected[str(sid)] if str(sid) in rejected else "not found"
            mismatches.append({"scenario": sid, "mode": "*", "variant": "*", "field": "__scenario__",
                               "expected": "present", "actual": actual, "classification": "UNCLASSIFIED"})
            continue
        for mode, fields in sorted((modes or {}).items()):
            runs = [r for r in results if str(r["scenario"]) == str(sid) and r["mode"] == mode]
            if not runs:
                mismatches.append({"scenario": sid, "mode": mode, "variant": "*", "field": "__run__",
                                   "expected": "run", "actual": "not run", "classification": "UNCLASSIFIED"})
                continue
            for r in runs:
                diffs = compare(fields, r["summary"])
                compared += len(fields or {})
                matched += len(fields or {}) - len(diffs)
                for field, exp, act in diffs:
                    mismatches.append({"scenario": sid, "mode": mode, "variant": r["variant"], "field": field,
                                       "expected": exp, "actual": act, "classification": "UNCLASSIFIED"})
    return mismatches, {"compared": compared, "matched": matched}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Duelist Ledger v0 (contract v%s)" % CONTRACT)
    ap.add_argument("--scenarios", help="scenario folder (default: scenarios/%s/, else scenarios/, "
                                        "else tests/fixtures)" % CONTRACT_DIR)
    ap.add_argument("--reveal", help="revealed expectations.json")
    ap.add_argument("--salt", help="revealed salt.txt")
    ap.add_argument("--seal", default=os.path.join("sealed", CONTRACT_DIR, "expectations.seal.json"),
                    help="seal file (default: sealed/%s/expectations.seal.json)" % CONTRACT_DIR)
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--subprocess", action="store_true", help="also run one demo session over a stdio pipe")
    ap.add_argument("--keep", action="store_true", help="keep per-run temp folders")
    ap.add_argument("--agent-child", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.agent_child:
        from duelist_ledger.agents import child_main
        child_main()
        return 0

    print(CAVEAT)
    print()
    print("Contract v%s" % CONTRACT)
    started = time.perf_counter()
    expectations, seal_info = None, {"status": "not requested"}
    if args.reveal or args.salt:
        if not (args.reveal and args.salt):
            print("ERROR: --reveal and --salt must be given together.")
            return 2
        seal_path = resolve_path(args.seal)
        res = check_reveal_files(seal_path, resolve_path(args.reveal), resolve_path(args.salt))
        if not res["ok"]:
            print("SEAL CHECK FAILED - aborting before any comparison.")
            print("  seal file: %s" % seal_path)
            print("  reason:    %s" % res["error"])
            print("  sealed:    %s" % res["commit"])
            print("  computed:  %s" % res["computed"])
            return 3
        expectations = res["expectations"]
        seal_info = {"status": "verified (%s salt reading)" % res["salt_reading"], "commit": res["commit"],
                     "seal_file": seal_path, "expectations_version": expectations.get("version")}
        print("Seal verified: %s" % res["commit"])
        if str(expectations.get("version")) != CONTRACT:
            seal_info["version_note"] = "expectations say version %r; this build is contract v%s" % (
                expectations.get("version"), CONTRACT)
            print("  NOTE: %s" % seal_info["version_note"])

    if args.skip_tests:
        tests = {"ok": True, "skipped": True, "run": 0, "failures": 0, "errors": 0}
    else:
        print("Running unit tests ...")
        tests = run_unit_tests()
        print("  %s: %d tests, %d failures, %d errors" % ("PASS" if tests["ok"] else "FAIL", tests["run"],
                                                          tests["failures"], tests["errors"]))
        if not tests["ok"]:
            print(tests["output_tail"])

    scen_dir = resolve_path(args.scenarios) if args.scenarios else default_scenario_dir()
    load_errors = []
    scenarios = load_scenarios(scen_dir, errors=load_errors)
    policy, sinks = load_config(os.path.join(ROOT, "config"))
    tmp_root = tempfile.mkdtemp(prefix="dl", dir=tempfile.gettempdir())
    results, n = [], 0
    print("Running %d scenarios from %s ..." % (len(scenarios), scen_dir))
    for err in load_errors:
        print("  LOAD ERROR (scenario skipped): %s" % err["error"])
    for sc in scenarios:
        for mode in modes_for(sc):
            for v in range(variant_count(sc)):
                n += 1
                results.append(run_one(sc, mode, v, os.path.join(tmp_root, str(n)), policy, sinks, keep=args.keep))
    demo = subprocess_demo(scenarios, policy, sinks, tmp_root) if args.subprocess else None

    strict_viol = sum(len(r["invariant_violations"]) for r in results if r["mode"] in STRICT_INVARIANT_MODES)
    strict_viol += sum(1 for r in results if r["mode"] in STRICT_INVARIANT_MODES and not r["summary"]["invariants_ok"])
    mismatches, match = (None, None)
    if expectations is not None:
        mismatches, match = expectation_diff(expectations, scenarios, results, load_errors)
    exit_code = 0 if tests["ok"] and strict_viol == 0 else 1
    payload = {
        "caveat": CAVEAT, "contract": CONTRACT, "unit_tests": tests, "seal": seal_info, "scenario_dir": scen_dir,
        "scenario_count": len(scenarios), "load_errors": load_errors, "runs": results, "metrics": compute(results),
        "strict_invariant_violations": strict_viol, "mismatches": mismatches,
        "expectation_match": match, "subprocess_demo": demo, "exit_code": exit_code,
        "seconds": round(time.perf_counter() - started, 2),
    }
    report.write(args.out, payload)
    if not args.keep:
        shutil.rmtree(tmp_root, ignore_errors=True)

    total = sum(r["replay"]["total"] for r in results)
    matched = sum(r["replay"]["matched"] for r in results)
    print("  %d runs; replay %d/%d; strict invariant violations %d" % (len(results), matched, total, strict_viol))
    if demo is not None:
        print("  stdio pipe demo: %s" % ("OK" if demo["ok"] else "FAILED %s" % demo))
    if mismatches is not None:
        print("  expectation fields matched %d/%d; %d mismatches (findings, not failures)" % (
            match["matched"], match["compared"], len(mismatches)))
    print("Report: %s" % os.path.join(args.out, "report.md"))
    print("Done in %.1fs, exit code %d." % (payload["seconds"], exit_code))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
