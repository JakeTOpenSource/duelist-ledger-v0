"""The outbox: staged actions waiting on the logical clock.

In plain words: risky actions (sending, paying, persisting) are not done at once. They wait
in this outbox until their release time. At release the gate checks everything again; an item
that is held or fails a check is discarded, and nothing is refunded.
"""


class Outbox:
    def __init__(self):
        self.items = []
        self.staged = 0

    def stage(self, **fields):
        """Add an item; returns it. Status starts as 'pending'."""
        self.staged += 1
        item = dict(fields)
        item.update(stage_id="st%d" % self.staged, n=self.staged, status="pending")
        self.items.append(item)
        return item

    def open_items(self, session):
        """Items of this session that are still pending or held, in release order."""
        live = [i for i in self.items if i["session"] == session and i["status"] in ("pending", "held")]
        return sorted(live, key=lambda i: (i["release_at"], i["n"]))

    def due(self, session, t):
        return [i for i in self.open_items(session) if i["release_at"] <= t]
