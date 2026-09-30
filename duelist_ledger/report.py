"""Writes out/results.json and out/report.md.

In plain words: the report opens with the caveat line, then per-mode metrics, a table of
what happened in each scenario, how many decisions replayed identically, invariant counts,
and the list of mismatches against the sealed expectations (if revealed).
"""

import json
import os

from . import CAVEAT, CONTRACT

OUT_OF_SCOPE = ("LLM agents, and the LLM monitor/duelist; cross-org operation (two houses, handshake, "
                "arbiter); attestation, TEEs, DPUs; real OS sandboxing (process isolation is by "
                "convention); an external witness (a local witness file stands in); Cedar/SMT; a human "
                "UI; the random-audit floor (specified for v1); natural-language content of any kind.")


def _pct(r):
    if not r or r.get("rate") is None:
        return "n/a"
    lo, hi = r["wilson95"]
    text = "%.1f%% (%d/%d, 95%% CI %.1f-%.1f%%)" % (100 * r["rate"], r["k"], r["n"], 100 * lo, 100 * hi)
    if "rule_of_three_upper" in r:
        text += ", rule-of-three <= %.1f%%" % (100 * r["rule_of_three_upper"])
    return text


def _cell(values):
    if isinstance(values, list):
        return ", ".join(str(v) for v in values) if values else "-"
    return str(values)


def write(out_dir, payload):
    os.makedirs(out_dir, exist_ok=True)
    slim = dict(payload)
    slim["runs"] = [{k: v for k, v in r.items() if k != "latencies"} for r in payload.get("runs", [])]
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(slim, fh, indent=1, sort_keys=True, ensure_ascii=False)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(payload))


def render(p):
    lines = [CAVEAT, "", "# Duelist Ledger v0: run report (contract v%s)" % CONTRACT, ""]
    ut = p.get("unit_tests") or {}
    seal = p.get("seal") or {}
    lines += ["- Unit tests: %s (%s run, %s failures, %s errors)" % (
        "PASS" if ut.get("ok") else ("SKIPPED" if ut.get("skipped") else "FAIL"),
        ut.get("run", 0), ut.get("failures", 0), ut.get("errors", 0)),
        "- Scenarios folder: `%s` (%d scenarios, %d runs)" % (p.get("scenario_dir"), p.get("scenario_count", 0),
                                                              len(p.get("runs", []))),
        "- Seal: %s" % seal.get("status", "not requested")]
    if seal.get("version_note"):
        lines.append("- Expectations version: %s" % seal["version_note"])
    for err in p.get("load_errors") or []:
        lines.append("- Load error (scenario skipped): %s" % err["error"])
    lines += ["- Exit code: %s" % p.get("exit_code"), ""]
    metrics = p.get("metrics") or {}
    lines += ["## Per-mode metrics", "",
              "| mode | runs | ASR | benign utility | utility under attack | false-HOLD rate | audit load (min/1000) | benign TRIPs | replay | invariant violations | decide p50/p99 (us) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for mode, m in sorted((metrics.get("per_mode") or {}).items()):
        lines.append("| %s | %d | %s | %s | %s | %s | %s%s | %d | %d/%d | %d | %s/%s |" % (
            mode, m["runs"], _pct(m["asr"]), _pct(m["benign_utility"]), _pct(m["utility_under_attack"]),
            _pct(m["false_hold_rate"]), m["audit_load_min_per_1000"],
            "" if m["within_audit_budget"] else " (over 60)", m["benign_trips"],
            m["replay_matched"], m["replay_total"], m["invariant_violations"],
            m["decide_p50_us"], m["decide_p99_us"]))
    bt = metrics.get("block_timing") or {}
    lines += ["", "Block timing (V2): pre-damage share %s; hard-block share (still blocked in A5) %s." % (
        _pct(bt.get("pre_damage_share")), _pct(bt.get("hard_block_share"))), ""]
    fh = metrics.get("false_hold_per_scenario_v2") or {}
    if fh:
        lines += ["False-HOLD per benign scenario (V2): " + "; ".join(
            "%s %d/%d" % (k, v["with_hold"], v["runs"]) for k, v in sorted(fh.items())), ""]
    lines += ["## Per-scenario outcomes (variant 0)", "",
              "| scenario | mode | outcomes | holds | trips | denies | adversary | goal | verify | replay |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in p.get("runs", []):
        if r["variant"] != 0:
            continue
        s = r["summary"]
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %d/%d |" % (
            r["scenario"], r["mode"], _cell(s["outcomes"]), _cell(s["holds"]), _cell(s["trips"]),
            _cell(s["denies"]), s["adversary_success"], s["goal_met"],
            "ok" if r["verify"]["ok"] else "BAD@%s" % r["verify"]["first_bad_seq"],
            r["replay"]["matched"], r["replay"]["total"]))
    total = sum(r["replay"]["total"] for r in p.get("runs", []))
    matched = sum(r["replay"]["matched"] for r in p.get("runs", []))
    viol = sum(len(r["invariant_violations"]) for r in p.get("runs", []))
    lines += ["", "## Correctness", "",
              "- Replay match: %s (%d/%d AUTHORIZE entries)" % (
                  "%.2f%%" % (100.0 * matched / total) if total else "n/a", matched, total),
              "- Invariant violations: %d (strict modes: %d)" % (viol, p.get("strict_invariant_violations", 0)), ""]
    mm = p.get("mismatches")
    lines += ["## Expectation mismatches", ""]
    if mm is None:
        lines += ["Not compared (no --reveal given).", ""]
    else:
        er = p.get("expectation_match") or {}
        lines += ["Expectation match rate: %s/%s compared fields." % (er.get("matched"), er.get("compared")), ""]
        if mm:
            lines += ["| scenario | mode | variant | field | expected | actual | classification |", "|---|---|---|---|---|---|---|"]
            for m in mm:
                lines.append("| %s | %s | %s | %s | `%s` | `%s` | %s |" % (
                    m["scenario"], m["mode"], m["variant"], m["field"], json.dumps(m["expected"]),
                    json.dumps(m["actual"]), m["classification"]))
        else:
            lines.append("No mismatches.")
        lines.append("")
    lines += ["## Out of scope for v0", "", OUT_OF_SCOPE, ""]
    return "\n".join(lines)
