"""Scripted agents (spec sec. 7). They speak JSON messages only, as if over a pipe, and every
message carries the session mac (sec. 3.8).

In plain words: each agent follows its script. A "compliant" agent is the worst case: it
obeys every directive it reads in untrusted data (send this file there, pay that payee, ...).
The other kinds differ only slightly: the schemer plans something outside the envelope, the
prober keeps re-submitting plans, the narrative fitter acts before planning and then tells a
story, and the silent agent just stops talking.

An agent is a generator: it yields a signed message and receives the gateway's reply. Running
it in another process (child_main) proves the same messages work over a real stdio pipe.
"""

import copy
import json
import re
import sys

from .canon import mac_of

FACT_RE = re.compile(r"FACT-[A-Za-z0-9_\-]*[A-Za-z0-9_]")
MAX_DEPTH = 8


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


class Agent:
    def __init__(self, spec):
        spec = spec or {}
        self.identity = spec.get("identity", "agent")
        self.kind = spec.get("kind", "compliant")
        self.declaration = spec.get("declaration")
        self.redeclarations = list(spec.get("redeclarations") or [])
        self.pre_ops = list(spec.get("pre_ops") or [])
        self.script = list(spec.get("script") or [])
        self.key = None

    # ---- the agent link ----
    def bind(self, key):
        """Receive the session key, once, over the bound transport (sec. 3.8)."""
        self.key = key

    def sign(self, msg):
        """The message with its mac under the session key (a random mac when no key was bound)."""
        out = dict(msg)
        out["mac"] = mac_of(self.key, out) if self.key else "unbound"
        return out

    # ---- the conversation ----
    def messages(self):
        """Yields signed messages; each yield receives the gateway's reply."""
        gen = self._messages()
        try:
            msg = next(gen)
            while True:
                reply = yield self.sign(msg)
                msg = gen.send(reply)
        except StopIteration:
            return

    def _messages(self):
        self.seq = 0
        self.ended = False
        self.handles, self.senders, self.facts = {}, {}, []
        self.to_override = None
        self.pay_override = None
        self.steps = []
        self.extra = 0
        for op in self.pre_ops:
            yield from self._op(op)
            if self.ended:
                return
        plans = [self.declaration] if self.declaration is not None else []
        if self.kind == "prober":
            plans += self.redeclarations
        for plan in plans:
            reply = yield {"op": "declare", "declaration": copy.deepcopy(plan)}
            if self._ended(reply):
                return
            if reply.get("status") == "OK":
                self.steps = [dict(s) for s in (plan or {}).get("steps") or [] if isinstance(s, dict)]
                break
        for op in self.script:
            name = op.get("op")
            if name == "stop":
                return
            if name == "finish":
                yield {"op": "finish"}
                return
            yield from self._op(op)
            if self.ended:
                return
        if self.kind == "silent":
            return
        yield {"op": "finish"}

    def _ended(self, reply):
        if not isinstance(reply, dict) or reply.get("status") == "SESSION_ENDED":
            self.ended = True
        return self.ended

    def _op(self, op):
        name = op.get("op")
        if name == "call":
            tool = op.get("tool")
            args = {k: self._arg(v) for k, v in (op.get("args") or {}).items()}
            if tool == "send_email" and self.to_override is not None:
                args["to"] = copy.deepcopy(self.to_override)
            if tool == "pay" and self.pay_override:
                args["payee"] = self.pay_override["payee"]
                if self.pay_override.get("amount") is not None:
                    args["amount"] = self.pay_override["amount"]
            yield from self._call(op.get("step_id"), tool, args, 0, op.get("seq"))
        elif name == "amend":
            reply = yield {"op": "amend", "kind": op.get("kind"), "step": copy.deepcopy(op.get("step"))}
            if not self._ended(reply) and reply.get("status") == "OK" and isinstance(op.get("step"), dict):
                self._remember_step(op.get("step"), op.get("kind"))
        elif name == "challenge":
            reply = yield {"op": "challenge", "request": copy.deepcopy(op.get("request"))}
            self._ended(reply)
        elif name == "narrate":
            reply = yield {"op": "narrate", "claims": copy.deepcopy(op.get("claims") or [])}
            self._ended(reply)

    def _remember_step(self, step, kind):
        for i, s in enumerate(self.steps):
            if s.get("step_id") == step.get("step_id"):
                if kind == "narrow" and step.get("remove"):
                    del self.steps[i]
                else:
                    self.steps[i] = dict(step)
                return
        self.steps.append(dict(step))

    def _arg(self, value):
        """Argument value forms (sec. 7.1). A handle_of / sender_of origin the agent never received
        becomes an unresolvable handle, so the proposal is undeclared (sec. 3.1, 4)."""
        if isinstance(value, dict):
            if "handle_of" in value:
                return {"handle": self.handles.get(value["handle_of"], "unknown:%s" % value["handle_of"])}
            if "sender_of" in value:
                if value["sender_of"] in self.senders:
                    return self.senders[value["sender_of"]]
                return {"handle": "unknown:sender_of:%s" % value["sender_of"]}
            if value.get("compose") == "facts":
                return " ".join(self.facts)
        return copy.deepcopy(value)

    def _first_step(self, tool):
        return next((s.get("step_id") for s in self.steps if s.get("tool") == tool), None)

    def _call(self, step_id, tool, args, depth, seq=None):
        self.seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else self.seq + 1
        reply = yield {"op": "propose", "seq": self.seq, "step_id": step_id, "tool": tool, "args": args}
        if self._ended(reply):
            return reply
        if reply.get("status") == "OK":
            results = reply.get("results") or []
            for r in results:
                self.handles[r.get("origin")] = r.get("handle")
                self.senders[r.get("origin")] = r.get("sender")
                self.facts.extend(FACT_RE.findall(_text(r.get("content"))))
            if depth < MAX_DEPTH:
                for r in results:
                    for d in r.get("directives") or []:
                        if self.ended:
                            return reply
                        yield from self._directive(d, depth + 1)
        return reply

    def _directive(self, d, depth):
        """Obey one inert directive record (spec sec. 7.2)."""
        if not isinstance(d, dict):
            return
        verb = d.get("verb") or d.get("op") or d.get("type")
        if verb == "send":
            args = {"to": d.get("target"), "body": "", "attach": d.get("object")}
            yield from self._call(self._first_step("send_email"), "send_email", args, depth)
        elif verb in ("replace_recipient", "reply_to"):
            self.to_override = d.get("target")
        elif verb == "pay":
            self.pay_override = {"payee": d.get("payee"), "amount": d.get("amount")}
        elif verb == "add_step":
            self.extra += 1
            sid = "x%d" % self.extra
            args = dict(d.get("args") or {})
            pinned = {k: (v if isinstance(v, list) else [v]) for k, v in args.items()}
            step = {"step_id": sid, "tool": d.get("tool"), "pinned": pinned, "free_guarded": {}, "max_calls": 1}
            reply = yield {"op": "amend", "kind": "widen", "step": step}
            if self._ended(reply) or reply.get("status") != "OK":
                return
            self.steps.append(step)
            yield from self._call(sid, d.get("tool"), args, depth)
        elif verb == "persist":
            args = {"key": d.get("key"), "content": d.get("content")}
            yield from self._call(self._first_step("persist_memory"), "persist_memory", args, depth)
        elif verb == "schedule":
            args = {"action": d.get("action"), "target": d.get("target")}
            yield from self._call(self._first_step("schedule"), "schedule", args, depth)
        elif verb == "write":
            args = {"path": d.get("path"), "content": d.get("content")}
            yield from self._call(self._first_step("write_workspace"), "write_workspace", args, depth)
        elif verb == "write_then_use":
            args = {"path": d.get("path"), "content": d.get("content")}
            reply = yield from self._call(self._first_step("write_workspace"), "write_workspace", args, depth)
            if self.ended or reply.get("status") != "OK":
                return
            reply = yield from self._call(self._first_step("read_file"), "read_file", {"path": d.get("path")}, depth)
            if self.ended or reply.get("status") != "OK" or not reply.get("results"):
                return
            self.to_override = {"handle": reply["results"][0]["handle"]}
        elif verb == "challenge":
            reply = yield {"op": "challenge", "request": copy.deepcopy(d.get("request"))}
            self._ended(reply)


def drive(gateway, agent, max_messages=2000, after_message=None):
    """Run one agent against the gateway in-process, over the link bound at SESSION_OPEN (the
    direct call from this agent object, sec. 3.8). Returns True if the agent sent finish.
    after_message(gateway, msg, reply, transport), if given, runs after every answered message
    (the harness uses it for the forge_message fault)."""
    link = gateway.link()
    agent.bind(link["key"])
    transport = link["transport"]
    gen = agent.messages()
    finished = False
    try:
        msg = next(gen)
    except StopIteration:
        msg = None
    count = 0
    while msg is not None and count < max_messages:
        count += 1
        wire = json.loads(json.dumps(msg))
        reply = gateway.handle(wire, transport)
        if msg.get("op") == "finish" and reply.get("status") != "LINK_REJECT":
            finished = True
        if after_message is not None:
            after_message(gateway, wire, reply, transport)
        try:
            msg = gen.send(json.loads(json.dumps(reply)))
        except StopIteration:
            msg = None
    gateway.end_session(finished)
    return finished


def child_main():
    """Agent side of the stdio pipe: line 1 is the agent spec, line 2 the session key (hex, handed
    over once), then message/reply lines."""
    spec = json.loads(sys.stdin.readline())
    agent = Agent(spec)
    key_line = sys.stdin.readline().strip()
    if key_line:
        agent.bind(bytes.fromhex(key_line))
    gen = agent.messages()
    try:
        msg = next(gen)
    except StopIteration:
        return
    while True:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            return
        try:
            msg = gen.send(json.loads(line))
        except StopIteration:
            return
