"""The stub advisory monitor (a P-source).

In plain words: a stand-in for a future model that looks at staged actions and may say
"suspect". It can only ask for a hold; it can never allow, release, resume or trip anything,
and the state machine rate-limits how often it may even ask.
"""


class Monitor:
    def __init__(self, config=None):
        cfg = config or {}
        mode = cfg.get("mode", "off")
        tools = cfg.get("suspect_tools") or cfg.get("tools") or []
        if isinstance(mode, dict):
            tools = mode.get("suspect_tools") or tools
            mode = "suspect_tools"
        if mode == "off" and cfg.get("suspect_tools"):
            mode = "suspect_tools"
        self.mode = mode
        self.tools = list(tools)

    def review(self, tool, args):
        """'SUSPECT' or 'OK'."""
        if self.mode == "suspect_all":
            return "SUSPECT"
        if self.mode == "suspect_tools" and tool in self.tools:
            return "SUSPECT"
        return "OK"
