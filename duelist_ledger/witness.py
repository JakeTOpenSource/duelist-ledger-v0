"""The separate witness.

In plain words: every so often the gate tells the witness "the diary is N entries long and its
last fingerprint is X". The witness writes that down in its own file, signed with its own key.
The witness never gets the gate's key and never touches the diary file, so a later rewrite of
the diary cannot also rewrite what the witness saw.
"""

import json
import os

from .canon import check_sig, dumps_line, sign


def _head_text(seq, head_hash):
    return dumps_line({"head_hash": head_hash, "seq": seq})


class Witness:
    """Receives (seq, head_hash) only. Holds its own key and its own heads file."""

    def __init__(self, heads_path, key):
        self._path = heads_path
        self._key = key
        os.makedirs(os.path.dirname(heads_path), exist_ok=True)
        self._fh = open(heads_path, "a+b")

    def close(self):
        if not self._fh.closed:
            self._fh.close()

    def record(self, seq, head_hash):
        """Append one signed head. Only integers and fingerprint strings are accepted."""
        if not isinstance(seq, int) or not isinstance(head_hash, str):
            raise TypeError("the witness accepts (seq:int, head_hash:str) only")
        row = {"seq": seq, "head_hash": head_hash, "wsig": sign(self._key, _head_text(seq, head_hash))}
        self._fh.write((dumps_line(row) + "\n").encode("utf-8"))
        self._fh.flush()

    def read_text(self):
        """The heads file as it is on disk now (published heads are readable by anyone)."""
        self._fh.flush()
        self._fh.seek(0)
        data = self._fh.read()
        self._fh.seek(0, 2)
        return data.decode("utf-8")

    def check(self):
        """True when every head in the file carries a valid witness signature."""
        return all(ok for _, ok in _rows(self._path, self._key, self.read_text()))


def _rows(path, key, text=None):
    if text is None:
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            out.append((None, False))
            continue
        ok = True
        if key is not None:
            ok = check_sig(key, _head_text(row.get("seq"), row.get("head_hash")), row.get("wsig"))
        out.append((row, ok))
    return out


def read_heads(path, key=None, text=None):
    """All witness heads as a list of {seq, head_hash, wsig, sig_ok}."""
    heads = []
    for row, ok in _rows(path, key, text):
        if row is None:
            heads.append({"seq": None, "head_hash": None, "wsig": None, "sig_ok": False})
        else:
            heads.append(dict(row, sig_ok=ok))
    return heads
