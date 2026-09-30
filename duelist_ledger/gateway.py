"""The gateway (Phase 1): the only door between the agent and the world.

In plain words, for each session it:
  1. opens the session and seals the house envelope (the agent never sees the envelope);
  2. keeps a clean room: nothing is executed or delivered until the agent commits a plan;
  3. checks the plan against the envelope (DECLARE);
  4. sends every proposed action through decide(), writes the inputs and the answer to the
     diary, and then executes, stages (escrow), holds for the scripted human, denies or trips;
  5. releases staged actions on the logical clock after re-checking them;
  6. reconciles its own records against the world's receipts, anchors the diary to the
     witness, and closes the session with ACCEPT / CLOSED / TRIP / REFUSED.

Modes A0 and A3 turn the gate into a pass-through (no clean room, no decide(), no escrow, no
SILENCE / SEQ_GAP / probes / monitor / challenge HOLDs) so the suite can show it has teeth. The
pipeline-integrity sensors still run: diary, receipts, reconciliation, anchoring with CHAIN
detection, and refusal of sessions after CHAIN.

A HOLD whose reasons need different resolvers (sec. 5.1) is settled group by group (S0 group,
session group, action group), in the rule-table order of each group's first reason. The first
group is settled on the HOLD decide() raised; each later group gets its own follow-on HOLD.
"""

import os
import re
import secrets
import time

from . import labels as L
from .budget import Fuse
from .canon import H, check_sig, dumps_line, sign
from .cases import Cases, pre_classify
from .decide import SESSION_CODES, as_number, canary_violation, compute_debits, decide, member, strings_in
from .escrow import Outbox
from .ledger import Ledger, verify as verify_ledger
from .policy import domain_of, policy_hash
from .reconcile import reconcile
from .seal import commit as seal_commit
from .state import State, level_of
from .witness import Witness

PASS_THROUGH = ("A0", "A3")
TIER_RAISING = ("H5_FUSE", "VERIFY_MISMATCH")
REPINNABLE = ("H3_PINNED_MISMATCH", "H4_TAINTED_GUARDED", "H8_FLOW")
NO_APPROVE_WHEN_TAINTED = ("H3_PINNED_MISMATCH", "H4_TAINTED_GUARDED")
PROBE_CODES = ("H1_NO_DECLARATION", "H2_NOT_DECLARED", "H3_PINNED_MISMATCH", "H4_TAINTED_GUARDED",
               "H6_PERSIST_AFTER_TAINT", "H7_AMEND_WIDEN", "H8_FLOW", "H9_VERBATIM_SELECTION")
S0 = "S0_SCOPE_HELD"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s\"'<>]+")
ANCHOR_EVERY = 20


def untrusted_strings_of(content, directives, vendors):
    """Email addresses, URLs and payee ids found in a result's content or directive fields."""
    found = []

    def add(s):
        if isinstance(s, str) and s and s not in found:
            found.append(s)

    for text in strings_in(content) + strings_in(directives):
        for m in EMAIL_RE.findall(text):
            add(m)
        for m in URL_RE.findall(text):
            add(m.rstrip(".,;)"))
        if text in vendors:
            add(text)
        for tok in re.findall(r"[A-Za-z0-9_.\-]+", text):
            if tok in vendors:
                add(tok)
    for d in directives or []:
        if isinstance(d, dict):
            add(d.get("payee"))
    return found


def validate_step(step, sinks):
    """Returns (normalised step, error). Error 'SCHEMA' for unknown tool or uncovered guarded slot."""
    if not isinstance(step, dict):
        return None, "SCHEMA"
    tool = step.get("tool")
    sink = sinks.get(tool) if isinstance(tool, str) else None
    if sink is None:
        return None, "SCHEMA"
    pinned = {}
    for slot, vals in (step.get("pinned") or {}).items():
        pinned[slot] = list(vals) if isinstance(vals, (list, tuple)) else [vals]
    free = dict(step.get("free_guarded") or {})
    for slot in sink.get("guarded") or []:
        if slot not in pinned and slot not in free:
            return None, "SCHEMA"
    max_calls = step.get("max_calls", 1)
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0:
        return None, "SCHEMA"
    return {"step_id": step.get("step_id"), "tool": tool, "pinned": pinned,
            "free_guarded": free, "max_calls": max_calls}, None


def envelope_violations(steps, envelope, sinks, registries):
    """The subset check of spec sec. 3.6. Returns a list of (step_id, tool, why)."""
    env = envelope or {}
    allowed = env.get("allowed_tools") or []
    dests = env.get("destinations") or {}
    max_money = as_number(env.get("max_money"))
    max_money = 0 if max_money is None else max_money
    out = []
    for st in steps:
        tool, sink = st["tool"], sinks[st["tool"]]
        if tool not in allowed:
            out.append((st["step_id"], tool, "tool not allowed"))
            continue
        for slot, vals in sorted(st["pinned"].items()):
            if slot not in (sink.get("guarded") or []):
                continue
            listed = dests.get("%s.%s" % (tool, slot)) or []
            regs = [x[len("registry:"):] for x in listed if isinstance(x, str) and x.startswith("registry:")]
            for v in vals:
                if member(v, listed):
                    continue
                if any(member(v, registries.get(r) or []) for r in regs):
                    continue
                num = as_number(v)
                if slot in (sink.get("numeric") or []) and num is not None and num <= max_money:
                    continue
                out.append((st["step_id"], tool, "pinned %s.%s outside envelope" % (tool, slot)))
        for slot, spec in sorted(st["free_guarded"].items()):
            listed = dests.get("%s.%s" % (tool, slot)) or []
            if isinstance(spec, dict):
                m = as_number(spec.get("max"))
                if m is None or m > max_money:
                    out.append((st["step_id"], tool, "free max over max_money"))
            elif "registry:%s" % spec not in listed:
                out.append((st["step_id"], tool, "registry %s not in envelope" % spec))
    limits = env.get("max_calls") or {}
    totals = {}
    for st in steps:
        totals[st["tool"]] = totals.get(st["tool"], 0) + st["max_calls"]
    for tool, total in sorted(totals.items()):
        if total > (limits.get(tool) or 0):
            sid = next(st["step_id"] for st in steps if st["tool"] == tool)
            out.append((sid, tool, "max_calls over envelope"))
    return out


class Session:
    """Everything the gateway tracks for one agent session."""

    def __init__(self, sid, identity, task):
        self.sid, self.identity, self.task = sid, identity, task
        self.scope = "L1:session:%s" % sid
        self.context = L.top()
        self.declaration = None
        self.probes = 0
        self.denies_by_tool = {}
        self.challenges = 0
        self.last_seq = 0
        self.status = "RUN"
        self.store = L.ValueStore()
        self.untrusted_strings = []
        self.written = []
        self.effects = []
        self.claims = None
        self.scope_discard = False
        self.tokens = {}
        self.items = 0
        self.decl_attempts = 0
        self.finished = False
        self.envelope = {}

    @property
    def tainted(self):
        return L.is_tainted(self.context)


class Gateway:
    def __init__(self, run_dir, policy, sinks, world, principal, *, mode="V2", monitor=None,
                 rules_enabled=None, hooks=None):
        self.run_dir = run_dir
        self.policy, self.sinks, self.world = policy, sinks, world
        self.principal, self.monitor, self.mode = principal, monitor, mode
        self.passthrough = mode in PASS_THROUGH
        self.rules_enabled = dict(rules_enabled) if rules_enabled is not None else {"R1": mode == "R2"}
        self.registries = world.registries
        self.canaries = world.canaries
        self.policy_hash = policy_hash(policy, sinks)
        self.gate_key = secrets.token_bytes(32)
        self.ledger_path = os.path.join(run_dir, "house", "ledger.jsonl")
        self.heads_path = os.path.join(run_dir, "witness", "heads.jsonl")
        self.blobs_path = os.path.join(run_dir, "house", "blobs.jsonl")
        self.ledger = Ledger(self.ledger_path, self.gate_key)
        self.witness = Witness(self.heads_path, secrets.token_bytes(32))
        self._blobs = set()
        self._blob_fh = open(self.blobs_path, "a", encoding="utf-8", newline="\n")
        p_src = policy.get("p_source") or {}
        self.state = State(p_src.get("per_session", 2), p_src.get("per_scenario", 5))
        self.fuse = Fuse(policy.get("fuse") or {})
        self.outbox = Outbox()
        self.cases = Cases(policy.get("strike_hold", 3), policy.get("common_mode_sessions", 3))
        self.hooks = hooks or {}
        self.t = 0
        self.session = None
        self.sessions = []
        self.effects = {}
        self.effect_n = 0
        self.gap_reported, self.bypass_reported, self.t4_items = set(), set(), set()
        self.seq_gap_links = set()
        self.origin_integrity = {}
        self.chain_held = False
        self.common_mode_held = False
        self.events = []
        self.outcomes = []
        self.cross_checks = []
        self.alarms = []
        self.latencies = []
        self.proposals = 0
        self.since_anchor = 0
        self.last_anchor_seq = 0
        self._anchoring = False
        self.chain_detected_seq = None

    # ---- diary helpers --------------------------------------------------------------------
    def _log(self, kind, scope, ref, body, reasons=(), actor="gateway"):
        s = self.session
        entry = self.ledger.append(t=self.t, session=s.sid if s else "", scope=scope, kind=kind,
                                   actor=actor, ref=ref, body=body, reasons=reasons,
                                   policy_hash=self.policy_hash)
        self.since_anchor += 1
        if self.since_anchor >= ANCHOR_EVERY and not self._anchoring:
            self.anchor()
        return entry

    def _blob(self, value):
        digest = H(value)
        if digest not in self._blobs:
            self._blobs.add(digest)
            self._blob_fh.write(dumps_line({"digest": digest, "value": value}) + "\n")
            self._blob_fh.flush()
        return {"$blob": digest}

    def close(self):
        """Close the house files (diary, witness heads, blobs)."""
        self.ledger.close()
        self.witness.close()
        if not self._blob_fh.closed:
            self._blob_fh.close()

    def _logged_args(self, sink, args):
        """Guarded values in clear (they are destinations); content as digests."""
        content = set(sink.get("content") or []) if sink else set()
        out = {}
        for slot in sorted(args):
            a = dict(args[slot])
            if slot in content or sink is None and slot not in ("to", "payee", "path", "url", "key"):
                a["value"] = self._blob(a.get("value"))
            out[slot] = a
        return out

    def _logged_inputs(self, inputs, sink):
        logged = dict(inputs)
        prop = dict(inputs["proposal"])
        prop["args"] = self._logged_args(sink, prop["args"])
        prop["payload_text"] = self._blob(prop.get("payload_text", ""))
        logged["proposal"] = prop
        return logged

    def anchor(self):
        """Send (seq, head) to the witness, then check the whole diary against all heads."""
        if self._anchoring:
            return
        self._anchoring = True
        try:
            res = verify_ledger(self.ledger_path, self.heads_path, ledger_text=self.ledger.read_text(),
                                heads_text=self.witness.read_text())
            seq, head = self.ledger.seq, self.ledger.head
            self.witness.record(seq, head)
            self.last_anchor_seq = seq
            self.since_anchor = 0
            self._log("ANCHOR", "L3", "anchor:%d" % seq, {"seq": seq, "head_hash": head})
            if not res["ok"]:
                self._chain_fault(res)
            if self.hooks.get("after_anchor"):
                self.hooks["after_anchor"](self)
        finally:
            self._anchoring = False

    def _chain_fault(self, res):
        if self.chain_held:
            return
        self.chain_held = True
        self.chain_detected_seq = res.get("first_bad_seq")
        self.alarms.append("CHAIN")
        self._log("ALARM", "L3", "org", {"code": "CHAIN", "first_bad_seq": res.get("first_bad_seq"),
                                         "why": res.get("why")}, ["CHAIN"])
        self.state.apply({"scope": "L3:org", "to": "HOLD"}, "D")
        self._raise_hold("L3", "L3:org", "CHAIN", ["CHAIN"], "org", {"first_bad_seq": res.get("first_bad_seq")})

    # ---- events, holds, cases ---------------------------------------------------------------
    def _event(self, etype, code, scope_name):
        s = self.session
        self.events.append({"type": etype, "code": code, "level": level_of(scope_name),
                            "scope": scope_name, "session": s.sid if s else None})

    def _cited_origins(self, label):
        """The untrusted origins in a label (a case cites those of the failing arg, or the context)."""
        return [o for o in (label or {}).get("origins", []) if self.origin_integrity.get(o, 0) < 2]

    def _open_case(self, primary, reasons, ref, *, failing_tainted=False, h2_no_slot=False,
                   origins=(), level="L0"):
        s = self.session
        pre = pre_classify(primary, failing_tainted, bool(s and s.tainted), h2_no_slot)
        case = self.cases.open(session=s.sid if s else None, identity=s.identity if s else None,
                               ref=ref, primary=primary, reasons=reasons, pre_class=pre,
                               origins=origins if pre == "injection-suspected" else ())
        self._log("CASE", level, case["case_id"], {"primary": primary, "pre_class": pre,
                                                    "ref": ref, "origins": case["origins"]}, reasons)
        if pre == "injection-suspected":
            for origin in self.cases.note_injection(case):
                self._common_mode(origin)
        return case

    def _finalize(self, case, resolution=None):
        before = self.cases.strikes_of(case["identity"])
        final = self.cases.finalize(case, resolution)
        return final, self.cases.strikes_of(case["identity"]) - before

    def _common_mode(self, origin):
        if self.common_mode_held:
            return
        self.common_mode_held = True
        self.state.apply({"scope": "L3:org", "to": "HOLD"}, "D")
        case = self._raise_hold("L3", "L3:org", "COMMON_MODE", ["COMMON_MODE"], "org", {"origin": origin})
        self._finalize(case)

    def _raise_hold(self, level, scope_name, primary, reasons, ref, body, **case_kw):
        """Log a HOLD, record the event, and open its case (returned)."""
        self._log("HOLD", level, ref, dict(body, primary=primary, scope=scope_name), reasons)
        self._event("CONFIRM" if primary == "CONFIRM_T3" else "HOLD", primary, scope_name)
        return self._open_case(primary, reasons, ref, level=level, **case_kw)

    def _item_scope(self, ref):
        s = self.session
        s.items += 1
        name = "L0:%s:%s#%d" % (s.sid, ref, s.items)
        self.state.register(name, s.scope)
        return name

    def _resolve_log(self, case, action, ref, level, extra=None):
        final, strikes = self._finalize(case, action)
        body = {"case": case["case_id"], "action": action, "final_class": final}
        if strikes:
            body["strike_added"] = strikes
        if extra:
            body.update(extra)
        self._log("RESOLVE", level, ref, body, [case["primary"]], actor="principal")

    def _count_probe_outcome(self, tool):
        """A denied action HOLD with a probe-counting primary, or an A7 DENY (sec. 5.5).

        Counted per tool; only the 2nd and later such outcome for a tool in the session adds a probe.
        """
        s = self.session
        s.denies_by_tool[tool] = s.denies_by_tool.get(tool, 0) + 1
        if s.denies_by_tool[tool] >= 2:
            self._add_probe()

    def _add_probe(self):
        s = self.session
        s.probes += 1
        if s.status == "RUN" and s.probes >= self.policy.get("probe_limit", 3):
            self._session_hold("PROBE", "probe", {"probes": s.probes})

    # ---- session-scope holds, closing and tripping ----------------------------------------------
    def _session_hold(self, code, ref, body):
        """A stand-alone L1 hold on the session (PROBE, SILENCE, VERIFY_MISMATCH)."""
        s = self.session
        case = self._raise_hold("L1", s.scope, code, [code], ref, body)
        return self._settle_session([code], case, ref)

    def _settle_session(self, codes, case, ref):
        """The principal resumes or closes a session HOLD. Returns 'resume'|'close'. PROBE closes."""
        s = self.session
        self.state.apply({"scope": s.scope, "to": "HOLD", "session": s.sid}, "D")
        choice = self.principal.session_hold(codes[0])
        if choice == "resume":
            self.state.apply({"scope": s.scope, "to": "RUN", "session": s.sid}, "H")
            if any(c in TIER_RAISING for c in codes):
                self.state.raise_tier_floor(s.sid)
            self._resolve_log(case, "resume", ref, "L1", {"tier_floor": self.state.tier_floor(s.sid)})
            return "resume"
        self.state.apply({"scope": s.scope, "to": "CLOSED", "session": s.sid}, "H")
        self._resolve_log(case, "close", ref, "L1")
        self._close_session("closed by %s" % codes[0])
        return "close"

    def _close_session(self, why):
        s = self.session
        s.status = "CLOSED"
        for item in self.outbox.open_items(s.sid):
            self._discard(item, why)

    def _trip_session(self, code, ref, body, *, failing_tainted=False, origins=()):
        s = self.session
        self.state.apply({"scope": s.scope, "to": "TRIP", "session": s.sid}, "D")
        self._log("TRIP", "L1", ref, dict(body, code=code, scope=s.scope), [code])
        self._event("TRIP", code, s.scope)
        case = self._open_case(code, [code], ref, failing_tainted=failing_tainted, origins=origins, level="L1")
        self._finalize(case)
        s.tokens.clear()
        for item in self.outbox.open_items(s.sid):
            self._discard(item, "session tripped")
        for kind, key, tainted in s.written:
            if tainted and self.world.quarantine(kind, key):
                self._log("QUARANTINE", "L1", "%s:%s" % (kind, key), {"kind": kind, "key": key})
        s.status = "TRIP"

    def _discard(self, item, why):
        if item["status"] in ("released", "discarded"):
            return
        item["status"] = "discarded"
        self._log("DISCARD", "L0", item["stage_id"], {"stage_id": item["stage_id"], "why": why})

    # ---- session lifecycle ------------------------------------------------------------------------
    def _verify_diary(self):
        """Full diary check against every witness head; the first failure raises ALARM + CHAIN."""
        res = verify_ledger(self.ledger_path, self.heads_path, ledger_text=self.ledger.read_text(),
                            heads_text=self.witness.read_text())
        if not res["ok"]:
            self._chain_fault(res)
        return res["ok"]

    def open_session(self, sid, task, identity, envelope):
        s = Session(sid, identity, task)
        self.session = s
        self.sessions.append(s)
        self.state.register(s.scope)
        s.envelope = envelope or {}
        self._verify_diary()
        salt = secrets.token_bytes(16)
        self._log("SESSION_OPEN", "L1", sid, {"task_digest": H(task), "agent": identity,
                                               "envelope_commit": seal_commit(s.envelope, salt)})
        refused = None
        if self.chain_held:
            refused = "CHAIN"
        elif self.cases.strikes_of(identity) >= self.policy.get("strike_hold", 3):
            refused = "STRIKES"
        if refused:
            s.status = "REFUSED"
            self._log("SESSION_CLOSE", "L1", sid, {"outcome": "REFUSED", "why": refused})
            self.outcomes.append("REFUSED")
            if self.mode == "A3":
                self.cross_checks.append("no_narrative")
            self.anchor()
            self.session = None
            return False
        return True

    def handle(self, msg):
        """One agent message in, one reply out. Every reply is coarse (no rule ids, no limits)."""
        s = self.session
        if s is None or s.status != "RUN":
            return {"status": "SESSION_ENDED"}
        self.t += 1
        op = msg.get("op") if isinstance(msg, dict) else None
        if op == "declare":
            reply = self._declare(msg.get("declaration"))
        elif op == "propose":
            reply = self._propose(msg)
        elif op == "amend":
            reply = self._amend(msg)
        elif op == "challenge":
            reply = self._challenge(msg.get("request"))
        elif op == "narrate":
            claims = msg.get("claims") or []
            s.claims = (s.claims or []) + list(claims)
            self._log("ANNOTATION", "L0", "narrate", {"claims": claims}, actor="agent")
            reply = {"status": "OK"}
        elif op == "finish":
            self._drain(s)
            reply = {"status": "OK"}
            s.finished = True
            return reply
        else:
            reply = {"status": "NOT_PERMITTED"}
        if s.status == "RUN":
            self._release_due(s)
        return reply if s.status == "RUN" else {"status": "SESSION_ENDED"}

    def end_session(self, finished):
        s = self.session
        if s is None:
            return
        if s.status == "RUN" and not finished and not self.passthrough:
            self._session_hold("SILENCE", "silence", {})
        if s.status == "RUN":
            self._drain(s)
        for item in self.outbox.open_items(s.sid):
            self._discard(item, "session ended")
        self._reconcile()
        if s.status == "TRIP":
            outcome = "TRIP"
        elif s.status == "CLOSED" or s.scope_discard:
            outcome = "CLOSED"
        else:
            outcome = "ACCEPT"
        body = {"outcome": outcome, "probes": s.probes, "challenges": s.challenges}
        if self.mode == "A3":
            body["cross_check"] = self._cross_check(s)
            self.cross_checks.append(body["cross_check"])
        self._log("SESSION_CLOSE", "L1", s.sid, body)
        self.outcomes.append(outcome)
        self.anchor()
        self.session = None

    def finish_scenario(self):
        """One last full diary check against all witness heads when the scenario ends."""
        self.session = None
        self._verify_diary()

    def _cross_check(self, s):
        if s.claims is None:
            return "no_narrative"
        claims = sorted(dumps_line([c.get("tool"), c.get("dest")]) for c in s.claims if isinstance(c, dict))
        effects = sorted(dumps_line([tool, dest]) for tool, dest in s.effects)
        return "consistent" if claims == effects else "divergent"

    # ---- DECLARE ------------------------------------------------------------------------------------
    def _declare(self, decl):
        s = self.session
        s.decl_attempts += 1
        ref = "decl%d" % s.decl_attempts
        if s.declaration is not None and not self.passthrough:
            self._log("DECLARE_REJECT", "L1", ref, {"why": "already declared"}, ["ALREADY_DECLARED"])
            return {"status": "NOT_PERMITTED"}
        steps, error = [], None
        if not isinstance(decl, dict) or not isinstance(decl.get("steps", []), list):
            error = "SCHEMA"
        else:
            for raw in decl.get("steps") or []:
                st, error = validate_step(raw, self.sinks)
                if error:
                    break
                steps.append(st)
        narrative = self._blob(decl.get("narrative", "")) if isinstance(decl, dict) else None
        if self.passthrough:
            raw_steps = decl.get("steps") if isinstance(decl, dict) else []
            steps = steps if not error else [dict(x) for x in raw_steps or [] if isinstance(x, dict)]
            return self._commit(steps, narrative, ref, approved=False)
        if error:
            self._log("DECLARE_REJECT", "L1", ref, {"code": "SCHEMA"}, ["SCHEMA"])
            return {"status": "NOT_PERMITTED"}
        bad = envelope_violations(steps, s.envelope, self.sinks, self.registries)
        if not bad:
            return self._commit(steps, narrative, ref, approved=False)
        decl_scope = "L1:decl:%s:%d" % (s.sid, s.decl_attempts)
        self.state.register(decl_scope, s.scope)
        self.state.apply({"scope": decl_scope, "to": "HOLD", "session": s.sid}, "D")
        case = self._raise_hold("L1", decl_scope, "H0_ENVELOPE", ["H0_ENVELOPE"], ref,
                                {"violations": [list(b) for b in bad]})
        action, _ = self.principal.resolve_l0("H0_ENVELOPE", bad[0][1], True, False, None)
        if action == "approve_once":
            self.state.apply({"scope": decl_scope, "to": "RUN", "session": s.sid}, "H")
            self._resolve_log(case, action, ref, "L1")
            return self._commit(steps, narrative, ref, approved=True)
        self.state.apply({"scope": decl_scope, "to": "CLOSED", "session": s.sid}, "H")
        self._resolve_log(case, "deny", ref, "L1")
        self._log("DECLARE_REJECT", "L1", ref, {"code": "H0_ENVELOPE"}, ["H0_ENVELOPE"])
        self._add_probe()
        return {"status": "NOT_PERMITTED"}

    def _commit(self, steps, narrative, ref, approved):
        s = self.session
        s.declaration = {"steps": steps, "declared_before_taint": not s.tainted}
        self._log("DECLARE", "L0", ref, {"steps": steps, "narrative": narrative,
                                          "declared_before_taint": not s.tainted,
                                          "approved_over_envelope": approved})
        return {"status": "OK"}

    # ---- AMEND and CHALLENGE ------------------------------------------------------------------
    def _is_narrower(self, new, old):
        if new["tool"] != old["tool"] or new["max_calls"] > old["max_calls"]:
            return False
        for slot, vals in new["pinned"].items():
            if slot in old["pinned"]:
                if not all(member(v, old["pinned"][slot]) for v in vals):
                    return False
            elif slot in old["free_guarded"]:
                spec = old["free_guarded"][slot]
                if isinstance(spec, dict):
                    limit = as_number(spec.get("max"))
                    if limit is None or any(as_number(v) is None or as_number(v) > limit for v in vals):
                        return False
                elif not all(member(v, self.registries.get(spec) or []) for v in vals):
                    return False
            elif slot in (self.sinks[new["tool"]].get("guarded") or []):
                return False
        for slot, spec in new["free_guarded"].items():
            if old["free_guarded"].get(slot) == spec:
                continue
            old_spec = old["free_guarded"].get(slot)
            if isinstance(spec, dict) and isinstance(old_spec, dict):
                a, b = as_number(spec.get("max")), as_number(old_spec.get("max"))
                if a is None or b is None or a > b:
                    return False
            else:
                return False
        return True

    def _amend(self, msg):
        s = self.session
        kind = msg.get("kind")
        raw = msg.get("step") or {}
        if s.declaration is None and not self.passthrough:
            self._log("AMEND", "L0", "amend", {"rejected": "no declaration"})
            return {"status": "NEEDS_DECLARATION"}
        steps = s.declaration["steps"] if s.declaration else []
        old = next((x for x in steps if x.get("step_id") == raw.get("step_id")), None) if isinstance(raw, dict) else None
        if kind == "narrow" and isinstance(raw, dict) and raw.get("remove") and old is not None:
            steps.remove(old)
            self._log("AMEND", "L0", "amend", {"kind": "narrow", "removed": old["step_id"]})
            return {"status": "OK"}
        step, error = validate_step(raw, self.sinks)
        if self.passthrough:
            self._apply_amend(step if not error else dict(raw) if isinstance(raw, dict) else {}, old)
            return {"status": "OK"}
        if error:
            self._log("AMEND", "L0", "amend", {"rejected": "SCHEMA"}, ["SCHEMA"])
            return {"status": "NOT_PERMITTED"}
        if kind == "narrow" and old is not None and self._is_narrower(step, old):
            self._apply_amend(step, old)
            return {"status": "OK"}
        ref = "amend:%s" % step.get("step_id")
        item = self._item_scope(ref)
        self.state.apply({"scope": item, "to": "HOLD", "session": s.sid}, "D")
        case = self._raise_hold("L0", item, "H7_AMEND_WIDEN", ["H7_AMEND_WIDEN"], ref, {"step": step})
        action, _ = self.principal.resolve_l0("H7_AMEND_WIDEN", step["tool"], not s.tainted, False, None)
        if action == "approve_once":
            self.state.apply({"scope": item, "to": "RUN", "session": s.sid}, "H")
            self._resolve_log(case, action, ref, "L0")
            self._apply_amend(step, old)
            return {"status": "OK"}
        self.state.apply({"scope": item, "to": "CLOSED", "session": s.sid}, "H")
        self._resolve_log(case, "deny", ref, "L0")
        self._log("DENY", "L0", ref, {"primary": "H7_AMEND_WIDEN"}, ["H7_AMEND_WIDEN"])
        self._count_probe_outcome(step["tool"])
        return {"status": "DENIED:NOT_PERMITTED"}

    def _apply_amend(self, step, old):
        s = self.session
        if s.declaration is None:
            s.declaration = {"steps": [], "declared_before_taint": not s.tainted}
        steps = s.declaration["steps"]
        if old is not None:
            steps[steps.index(old)] = step
        else:
            steps.append(step)
        self._log("AMEND", "L0", "amend:%s" % step.get("step_id"), {"step": step})

    def _challenge(self, request):
        s = self.session
        s.challenges += 1
        ref = "challenge%d" % s.challenges
        self._log("CHALLENGE", "L0", ref, {"request": self._blob(request)}, actor="agent")
        if self.passthrough:
            return {"status": "OK"}
        item = self._item_scope(ref)
        self.state.apply({"scope": item, "to": "HOLD", "session": s.sid}, "D")
        case = self._raise_hold("L0", item, "CHALLENGE", ["CHALLENGE"], ref, {})
        if self.principal.challenge(request):
            self.state.apply({"scope": item, "to": "RUN", "session": s.sid}, "H")
            self._resolve_log(case, "approve_once", ref, "L0")
            step = request.get("step") if isinstance(request, dict) else None
            if step is not None:
                st, err = validate_step(step, self.sinks)
                if not err:
                    self._apply_amend(st, None)
            return {"status": "OK"}
        self.state.apply({"scope": item, "to": "CLOSED", "session": s.sid}, "H")
        self._resolve_log(case, "deny", ref, "L0")
        self._log("DENY", "L0", ref, {"primary": "CHALLENGE"}, ["CHALLENGE"])
        return {"status": "DENIED:NOT_PERMITTED"}

    # ---- PROPOSE ------------------------------------------------------------------------------
    def _resolve_args(self, raw_args):
        s = self.session
        args = {}
        for slot in sorted(raw_args):
            val = raw_args[slot]
            if isinstance(val, dict) and set(val) == {"handle"}:
                rec = s.store.get(val["handle"])
                if rec is None:
                    return None
                args[slot] = {"value": rec["content"], "label": L.copy(rec["label"]), "handle": val["handle"]}
            else:
                args[slot] = {"value": val, "label": L.copy(s.context)}
        return args

    def _payload(self, sink, args):
        label, texts = L.top(), []
        if not sink:
            return label, ""
        for slot in sink.get("content") or []:
            if slot not in args:
                continue
            label = L.join(label, args[slot]["label"])
            val = args[slot]["value"]
            if slot in (sink.get("attach") or []):
                paths = val if isinstance(val, list) else [val]
                for p in paths:
                    view = self.world.file_view(p)
                    if view:
                        texts.append(view[0] if isinstance(view[0], str) else dumps_line(view[0]))
                        label = L.join(label, view[1])
            else:
                texts.append(val if isinstance(val, str) else dumps_line(val))
        return label, "\n".join(texts)

    def _scope_states(self, sink):
        """Effective state of the session, link and org scopes this action touches."""
        s = self.session
        names = [s.scope, "L3:org", "L2:agent->gate"]
        if sink:
            names.append("L2:gate->world:%s" % sink["sink_class"])
        return {name: self.state.effective(name) for name in names}

    def _propose(self, msg):
        s = self.session
        seq = msg.get("seq")
        tool = msg.get("tool")
        sink = self.sinks.get(tool) if isinstance(tool, str) else None
        raw_args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
        ref = "%s:p%s" % (s.sid, seq)
        self.proposals += 1
        args = self._resolve_args(raw_args)
        logged = self._logged_args(sink, args) if args is not None else {"unresolved": True}
        self._log("PROPOSE", "L0", ref, {"seq": seq, "step_id": msg.get("step_id"), "tool": tool,
                                          "args": logged}, actor="agent")
        if not self.passthrough:
            if isinstance(seq, bool) or not isinstance(seq, int) or seq != s.last_seq + 1:
                if isinstance(seq, int) and not isinstance(seq, bool):
                    s.last_seq = seq
                link = "L2:agent->gate"
                self.state.apply({"scope": link, "to": "HOLD"}, "D")
                self.seq_gap_links.add(link)
                case = self._raise_hold("L2", link, "SEQ_GAP", ["SEQ_GAP"], ref, {"seq": seq})
                self._finalize(case)
                return {"status": "HELD"}
            s.last_seq = seq
        elif isinstance(seq, int):
            s.last_seq = seq
        if args is None or sink is None:
            return {"status": "NOT_PERMITTED"}
        payload_label, payload_text = self._payload(sink, args)
        if self.passthrough:
            debits = compute_debits(sink, args, self._step_for_passthrough(msg, tool))
            self._apply_debits(debits)
            return self._execute(sink, tool, args, payload_label, ref, token=None)
        fuse_cfg = (self.policy.get("fuse") or {}).get(sink["sink_class"])
        if fuse_cfg:
            self.fuse.bump(s.sid, sink["sink_class"], self.t)
        inputs = self._inputs(msg, tool, sink, args, payload_label, payload_text)
        t0 = time.perf_counter()
        decision = decide(inputs)
        self.latencies.append(time.perf_counter() - t0)
        self._log("AUTHORIZE", decision["scope"], ref,
                  {"inputs": self._logged_inputs(inputs, sink), "decision": decision},
                  decision["reasons"])
        return self._dispatch(decision, inputs, tool, sink, args, payload_label, payload_text, ref)

    def _step_for_passthrough(self, msg, tool):
        s = self.session
        steps = (s.declaration or {}).get("steps") or []
        st = next((x for x in steps if x.get("step_id") == msg.get("step_id")), None)
        return st["step_id"] if st is not None and st.get("tool") == tool else None

    def _inputs(self, msg, tool, sink, args, payload_label, payload_text):
        s = self.session
        decl = None
        if s.declaration is not None:
            used = self.state.session_snapshot(s.sid)
            decl = {"declared_before_taint": s.declaration["declared_before_taint"],
                    "steps": [dict(st, used=used.get("step:%s" % st["step_id"], 0))
                              for st in s.declaration["steps"]]}
        session_counters = {k: v for k, v in self.state.session_snapshot(s.sid).items()
                            if not k.startswith("step:")}
        return {
            "mode": self.mode, "policy": self.policy, "sinks": self.sinks,
            "registries": self.registries, "canaries": self.canaries,
            "session": s.sid, "declaration": decl,
            "proposal": {"seq": msg.get("seq"), "step_id": msg.get("step_id"), "tool": tool,
                         "args": args, "payload_label": payload_label, "payload_text": payload_text},
            "context_label": L.copy(s.context), "session_tainted": s.tainted,
            "scope_states": self._scope_states(sink),
            "counters": self.state.counters.snapshot(), "session_counters": session_counters,
            "fuse_state": self.fuse.snapshot(s.sid), "tier_floor": self.state.tier_floor(s.sid),
            "t": self.t, "untrusted_strings": [dict(e) for e in s.untrusted_strings],
            "rules_enabled": dict(self.rules_enabled),
        }

    def _dispatch(self, decision, inputs, tool, sink, args, payload_label, payload_text, ref):
        s = self.session
        outcome = decision["outcome"]
        if outcome == "TRIP":
            self._trip_session(decision["primary"], ref, {"tool": tool}, origins=self._cited_origins(s.context))
            return {"status": "SESSION_ENDED"}
        if outcome == "DENY":
            self._log("DENY", decision["scope"], ref, {"primary": decision["primary"], "strict": True},
                      decision["reasons"])
            self._event("DENY", decision["primary"], decision["held_scope"] or "L0")
            case = self._open_case(decision["primary"], decision["reasons"], ref, level=decision["scope"],
                                   **self._case_facts(decision, args))
            self._finalize(case)
            self._count_probe_outcome(tool)
            return {"status": "DENIED:NOT_PERMITTED"}
        if outcome == "HOLD":
            verdict, coarse = self._resolve_hold(decision, tool, sink, args, ref)
            if verdict != "allow":
                return {"status": "SESSION_ENDED"} if s.status != "RUN" else {"status": "DENIED:%s" % coarse}
        return self._authorize(decision, tool, sink, args, payload_label, payload_text, ref)

    def _case_facts(self, decision, args):
        """What every case of this decision is classified on (sec. 4, 5.6).

        failing_tainted is the decision's; h2_no_slot says the H2 reason named no slot; the cited
        origins are the untrusted origins in the failing argument's label.
        """
        slot = decision["failing_slot"]
        origins = []
        if decision["failing_tainted"] and slot and slot in args:
            origins = self._cited_origins(args[slot]["label"])
        h2 = next((d for d in decision["details"] if d["code"] == "H2_NOT_DECLARED"), None)
        return {"failing_tainted": decision["failing_tainted"], "origins": origins,
                "h2_no_slot": h2 is not None and h2.get("slot") is None}

    @staticmethod
    def _groups(details):
        """A HOLD's reasons split by resolver (S0 / session / action), ordered by each group's
        first reason in rule-table order (details arrive sorted in that order)."""
        order, groups = [], {}
        for d in details:
            kind = "S0" if d["code"] == S0 else "session" if d["code"] in SESSION_CODES else "action"
            if kind not in groups:
                groups[kind] = []
                order.append(kind)
            groups[kind].append(d)
        return [(kind, groups[kind]) for kind in order]

    def _resolve_hold(self, decision, tool, sink, args, ref):
        """Settle a HOLD group by group (sec. 5.1). Returns ('allow', None) or ('deny', coarse).

        The first group is settled on the HOLD decide() raised (primary = the decision's primary,
        reasons = all of them). Each later group gets a follow-on HOLD of its own, with its own case.
        S0 denies and stops; a session group resumes or closes; the action group is one principal
        decision whose options are the intersection of its reasons' options.
        """
        s = self.session
        facts = self._case_facts(decision, args)
        for n, (kind, group) in enumerate(self._groups(decision["details"])):
            first = group[0]
            codes = []
            for d in group:
                if d["code"] not in codes:
                    codes.append(d["code"])
            reasons = decision["reasons"] if n == 0 else codes
            body = {"tool": tool, "group": kind, "follow_on": n > 0}
            item = None
            if kind == "session":
                held = s.scope
            elif kind == "S0":
                held = first["held"]
            else:
                item = self._item_scope(ref)
                self.state.apply({"scope": item, "to": "HOLD", "session": s.sid}, "D")
                held = item if first["held"] == "L0:item" else first["held"]
            case = self._raise_hold(first["scope"], held, first["code"], reasons, ref, body, **facts)
            if kind == "S0":
                self._resolve_log(case, "unresolvable", ref, first["scope"])
                self._log("DENY", first["scope"], ref, {"primary": first["code"]}, reasons)
                return "deny", "HELD"
            if kind == "session":
                if self._settle_session(codes, case, ref) == "close":
                    return "deny", "SESSION_ENDED"
                continue
            coarse = self._settle_action(decision, group, codes, case, item, tool, sink, args, ref)
            if coarse is not None:
                return "deny", coarse
        return "allow", None

    def _settle_action(self, decision, group, codes, case, item, tool, sink, args, ref):
        """One principal decision for the action group. Returns None (proceed) or the coarse code."""
        s = self.session
        first = group[0]
        approve_ok = not (decision["failing_tainted"] and any(c in NO_APPROVE_WHEN_TAINTED for c in codes))
        slot = next((d["slot"] for d in group if d.get("slot")), None)
        repin_ok = all(c in REPINNABLE for c in codes) and slot in (sink.get("guarded") or [])
        held_value = args[slot]["value"] if slot and slot in args else None
        action, value = self.principal.resolve_l0(first["code"], tool, approve_ok, repin_ok, held_value)
        if action in ("approve_once", "repin"):
            self.state.apply({"scope": item, "to": "RUN", "session": s.sid}, "H")
            extra = None
            if action == "repin":
                args[slot] = {"value": value, "label": L.top(), "repinned": True}
                extra = {"slot": slot, "value": value}
            self._resolve_log(case, action, ref, first["scope"], extra)
            return None
        self.state.apply({"scope": item, "to": "CLOSED", "session": s.sid}, "H")
        self._resolve_log(case, "deny", ref, first["scope"])
        self._log("DENY", first["scope"], ref, {"primary": first["code"]}, codes)
        if first["code"] in PROBE_CODES:
            self._count_probe_outcome(tool)
        return "NEEDS_DECLARATION" if first["code"] == "H1_NO_DECLARATION" else "NOT_PERMITTED"

    def _apply_debits(self, debits):
        s = self.session
        for d in debits:
            if "step" in d["counters"]:
                self.state.debit(d["key"], d["amount"], s.sid, counters=("step",))
            else:
                self.state.debit(d["key"], d["amount"], s.sid, counters=tuple(d["counters"]))

    def _mint(self, decision, args):
        s = self.session
        plain = {k: v["value"] for k, v in args.items()}
        token = {"decl_step": next((d["key"][5:] for d in decision["debits"] if d["key"].startswith("step:")), None),
                 "args_hash": H(plain), "nonce": secrets.token_hex(8),
                 "expires_t": self.t + 2 * max([int(v) for v in (self.policy.get("escrow_window") or {"1": 1}).values()] + [1])}
        token["sig"] = sign(self.gate_key, H({k: v for k, v in token.items()}))
        s.tokens[token["nonce"]] = token
        return token

    def _token_ok(self, token, args, late_ok=False):
        """Issued, not revoked, signed, unexpired (late_ok: the gate itself held the item past it),
        and the args hash unchanged."""
        s = self.session
        if not token or token.get("nonce") not in s.tokens:
            return False
        core = {k: v for k, v in token.items() if k != "sig"}
        if not check_sig(self.gate_key, H(core), token.get("sig")):
            return False
        if self.t > token["expires_t"] and not late_ok:
            return False
        return H({k: v["value"] for k, v in args.items()}) == token["args_hash"]

    def _authorize(self, decision, tool, sink, args, payload_label, payload_text, ref):
        s = self.session
        self._apply_debits(decision["debits"])
        token = self._mint(decision, args)
        if sink["rev"] in ("R0", "R1"):
            return self._execute(sink, tool, args, payload_label, ref, token)
        tier = decision["tier"]
        window = (self.policy.get("escrow_window") or {}).get(str(min(max(tier, 1), 3)), 1)
        item = self.outbox.stage(session=s.sid, tool=tool, sink_class=sink["sink_class"], ref=ref,
                                 args={k: dict(v) for k, v in args.items()}, token=token, tier=tier,
                                 release_at=self.t + int(window), payload_label=payload_label,
                                 payload_text=payload_text)
        self._log("ESCROW", "L0", ref, {"stage_id": item["stage_id"], "release_at": item["release_at"],
                                         "tier": tier, "args_hash": token["args_hash"]})
        if self.hooks.get("on_escrow"):
            self.hooks["on_escrow"](self, item)
        if self.monitor is not None and self.monitor.review(tool, item["args"]) == "SUSPECT":
            self._monitor_hold(item)
        return {"status": "OK", "staged": True}

    def _monitor_hold(self, item):
        s = self.session
        scope = "L0:%s:%s" % (s.sid, item["stage_id"])
        self.state.register(scope, s.scope)
        res = self.state.apply({"scope": scope, "to": "HOLD", "session": s.sid}, "P")
        if res["kind"] == "FLAG":
            self._log("FLAG", "L0", item["stage_id"], {"source": "monitor", "verdict": "SUSPECT"},
                      ["MONITOR"], actor="monitor")
            if res["alarm"]:
                self.alarms.append(res["alarm"])
                self._log("ALARM", "L3", "p_source", {"code": res["alarm"]}, [res["alarm"]], actor="monitor")
            return
        if not res["applied"]:
            return
        case = self._raise_hold("L0", scope, "MONITOR", ["MONITOR"], item["stage_id"], {"source": "monitor"})
        if self.principal.monitor():
            self.state.apply({"scope": scope, "to": "RUN", "session": s.sid}, "H")
            self._resolve_log(case, "approve_once", item["stage_id"], "L0")
        else:
            self.state.apply({"scope": scope, "to": "CLOSED", "session": s.sid}, "H")
            self._resolve_log(case, "deny", item["stage_id"], "L0")
            self._discard(item, "monitor hold denied")

    # ---- execution, release, reconcile ---------------------------------------------------------
    def _execute(self, sink, tool, args, payload_label, ref, token, kind="EXECUTE"):
        s = self.session
        plain = {k: v["value"] for k, v in args.items()}
        self.effect_n += 1
        eid = "e%d" % self.effect_n
        self.effects[eid] = sink["sink_class"]
        args_hash = H(plain)
        self._log(kind, "L0", ref, {"effect_id": eid, "tool": tool, "args_hash": args_hash,
                                     "args": self._logged_args(sink, args)})
        results = self.world.apply(tool, sink["sink_class"], plain, eid, payload_label)
        if tool == "write_workspace":
            s.written.append(("file", plain.get("path"), s.tainted))
        elif tool == "persist_memory":
            s.written.append(("memory", plain.get("key"), s.tainted))
        elif tool == "schedule":
            s.written.append(("schedule", len(self.world.schedules) - 1, s.tainted))
        if sink["rev"] != "R0":
            dest_slot = sink.get("dest_slot") or ((sink.get("guarded") or [None])[0])
            s.effects.append((tool, plain.get(dest_slot)))
        self._reconcile()
        self._verify_effect(eid, sink["sink_class"], args_hash, ref)
        delivered = self._deliver(results)
        self._log("VERIFY", "L0", ref, {"effect_id": eid,
                                         "results": [{"origin": r["origin"], "digest": H(r["content"])}
                                                     for r in delivered]})
        return {"status": "OK", "results": delivered}

    def _deliver(self, results):
        s = self.session
        out = []
        vendors = self.registries.get("vendors") or []
        for r in results:
            h = s.store.put(r["content"], r["label"], r["origin"], r.get("sender"), r.get("directives"))
            s.context = L.join(s.context, r["label"])
            prev = self.origin_integrity.get(r["origin"])
            integ = r["label"]["integrity"]
            self.origin_integrity[r["origin"]] = integ if prev is None else min(prev, integ)
            if L.is_tainted(r["label"]):
                s.untrusted_strings.append({"origin": r["origin"], "sender": r.get("sender"),
                                            "strings": untrusted_strings_of(r["content"], r.get("directives") or [], vendors)})
            out.append({"handle": h, "content": r["content"], "origin": r["origin"],
                        "sender": r.get("sender"), "directives": list(r.get("directives") or [])})
        return out

    def _verify_effect(self, eid, sink_class, args_hash, ref):
        rcpt = self.world.receipt_for(eid)
        if rcpt is None or self.session is None or self.session.status != "RUN":
            return
        if rcpt["sink_class"] != sink_class or rcpt["args_digest"] != args_hash:
            self._session_hold("VERIFY_MISMATCH", ref, {"effect_id": eid})

    def _reconcile(self):
        res = reconcile(self.effects, self.world.receipts)
        for rcpt in res["bypass"]:
            if rcpt["effect_id"] in self.bypass_reported:
                continue
            self.bypass_reported.add(rcpt["effect_id"])
            link = "L2:gate->world:%s" % rcpt["sink_class"]
            self.state.apply({"scope": link, "to": "TRIP"}, "D")
            self._log("TRIP", "L2", link, {"code": "T3_BYPASS", "scope": link,
                                            "effect_id": rcpt["effect_id"]}, ["T3_BYPASS"])
            self._event("TRIP", "T3_BYPASS", link)
            self.alarms.append("GATE_FAULT")
            self._log("ALARM", "L3", "org", {"code": "GATE_FAULT", "link": link}, ["GATE_FAULT"])
            case = self._open_case("T3_BYPASS", ["T3_BYPASS"], link, level="L2")
            self._finalize(case)
        for eid, cls in res["gaps"]:
            if eid in self.gap_reported:
                continue
            self.gap_reported.add(eid)
            link = "L2:gate->world:%s" % cls
            self.state.apply({"scope": link, "to": "HOLD"}, "D")
            case = self._raise_hold("L2", link, "RECEIPT_GAP", ["RECEIPT_GAP"], link, {"effect_id": eid})
            self._finalize(case)
        if not res["bypass"] and not res["gaps"]:
            for link in sorted(self.seq_gap_links):
                if self.state.own(link) == "HOLD":
                    self.state.apply({"scope": link, "to": "RUN", "predicate": "reconcile_ok"}, "D")
                    self._log("RESOLVE", "L2", link, {"action": "cleared", "predicate": "reconcile_ok"},
                              ["SEQ_GAP"])
            self.seq_gap_links.clear()

    def _release_due(self, s):
        for item in self.outbox.due(s.sid, self.t):
            if s.status != "RUN":
                break
            self._release(item)

    def _drain(self, s):
        """Advance the clock to each release time in order. Every step is a release pass, so an
        item held on a scope is re-checked each time; anything still held at the end is discarded
        (and the session will end CLOSED)."""
        while s.status == "RUN":
            self._release_due(s)
            later = [i["release_at"] for i in self.outbox.open_items(s.sid) if i["release_at"] > self.t]
            if not later or s.status != "RUN":
                break
            self.t = min(later)
        for item in self.outbox.open_items(s.sid):
            if item["status"] == "held" and s.status == "RUN":
                s.scope_discard = True
            self._discard(item, "never cleared by drain")

    def _release(self, item):
        """Second commit point: re-check scopes, token, args hash, canaries; confirm tier 3."""
        s = self.session
        if item["status"] not in ("pending", "held"):
            return
        if s.status != "RUN":
            self._discard(item, "session %s" % s.status)
            return
        for name in ("L3:org", "L2:agent->gate", "L2:gate->world:%s" % item["sink_class"]):
            if self.state.effective(name) != "RUN":
                if item["status"] != "held":
                    item["status"] = "held"
                    item["was_held"] = True
                    case = self._raise_hold(level_of(name), name, S0, [S0],
                                            item["stage_id"], {"stage_id": item["stage_id"], "at": "release"})
                    self._finalize(case)
                return
        item["status"] = "pending"
        if not self._token_ok(item["token"], item["args"], late_ok=item.get("was_held", False)):
            self.t4_items.add(item["stage_id"])
            self._trip_session("T4_ARGS_MISMATCH", item["stage_id"], {"stage_id": item["stage_id"]})
            return
        token = canary_violation(self.sinks[item["tool"]], item["args"], item["payload_text"], self.canaries)
        if token is not None:
            self._trip_session("T2_CANARY", item["stage_id"], {"stage_id": item["stage_id"], "at": "release"},
                               origins=self._cited_origins(s.context))
            return
        if item["tier"] >= 3:
            scope = "L0:%s:%s:confirm" % (s.sid, item["stage_id"])
            self.state.register(scope, s.scope)
            self.state.apply({"scope": scope, "to": "HOLD", "session": s.sid}, "D")
            case = self._raise_hold("L0", scope, "CONFIRM_T3", ["CONFIRM_T3"], item["stage_id"],
                                    {"tool": item["tool"]})
            plain = {k: v["value"] for k, v in item["args"].items()}
            if self.principal.confirm_t3(item["tool"], plain):
                self.state.apply({"scope": scope, "to": "RUN", "session": s.sid}, "H")
                self._resolve_log(case, "confirm", item["stage_id"], "L0")
            else:
                self.state.apply({"scope": scope, "to": "CLOSED", "session": s.sid}, "H")
                self._resolve_log(case, "deny", item["stage_id"], "L0")
                self._discard(item, "CONFIRM_T3 denied")
                return
        s.tokens.pop(item["token"]["nonce"], None)
        item["status"] = "released"
        self._execute(self.sinks[item["tool"]], item["tool"], item["args"], item["payload_label"],
                      item["stage_id"], item["token"], kind="RELEASE")
