"""Budgets: one-way counters, the heat fuse, and the risk tier.

In plain words: counters only ever go up (nothing is refunded). The fuse is a "heat" number
per session and tool class that cools down over logical time and jumps by one per request;
too much heat holds the session. The tier says how carefully an action must be released.
"""


class Counters:
    """A dict of numbers that can only grow."""

    def __init__(self):
        self._c = {}

    def add(self, key, amount):
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            return False
        self._c[key] = self._c.get(key, 0) + amount
        return True

    def get(self, key, default=0):
        return self._c.get(key, default)

    def snapshot(self):
        return dict(self._c)


class Fuse:
    """Heat per (session, sink_class): heat = heat * decay**(t - t_last) + 1 on each proposal."""

    def __init__(self, config):
        self.config = config or {}
        self._state = {}

    def bump(self, session, sink_class, t):
        cfg = self.config.get(sink_class)
        if not cfg:
            return None
        prev = self._state.get((session, sink_class))
        if prev is None:
            heat = 1.0
        else:
            heat = prev["heat"] * (float(cfg.get("decay", 1.0)) ** (t - prev["t_last"])) + 1.0
        self._state[(session, sink_class)] = {"heat": heat, "t_last": t}
        return dict(self._state[(session, sink_class)])

    def snapshot(self, session):
        return {cls: dict(v) for (sid, cls), v in sorted(self._state.items()) if sid == session}


def compute_tier(base_tier, persistent, amount, period_money, tier3_money, tier_floor, money_band=True):
    """tier = max(base tier, 2 if persistent, 3 for big or cumulative money, session floor)."""
    tier = int(base_tier or 0)
    if persistent:
        tier = max(tier, 2)
    if money_band and amount is not None and tier3_money is not None:
        if amount >= tier3_money or (period_money or 0) + amount >= tier3_money:
            tier = max(tier, 3)
    return max(tier, int(tier_floor or 0))
