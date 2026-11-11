"""Format-preserving JSON documents — the suite edits a game's data files without reformatting them.

A game's data is edited by hand (Notepad), by game build sessions and by the suite. A save must change exactly the
bytes of the value that changed: the rest of the file — indentation, key order, escapes, line endings, a byte-order
mark, unknown fields — stays byte for byte. So a document keeps its original text and a map of where every value sits
in it; `set()` replaces one value's span, `add()` inserts one member with the indentation its siblings use. A save
with no edit gives back the original bytes.

    doc = JsonDoc.from_bytes(path.read_bytes())
    doc.get("/lines/3/text")
    doc.set("/lines/3/text", "A better line.")
    doc.add("/lines/3", "status", "approved")
    path.write_bytes(doc.to_bytes())          # (the suite never writes directly — see safesave.py)

Pointers are RFC 6901 ("/lines/3/text"; "~1" is "/" and "~0" is "~" inside a key) or a list of keys and indices.
Standard library only.
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field

BOM = b"\xef\xbb\xbf"
_NUM = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_STR = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"', re.S)
_WS = " \t\n\r"


class JsonDocError(ValueError):
    """A file that is not JSON, or a pointer/edit that cannot apply — the message is in plain words."""


@dataclass
class Node:
    kind: str                       # object | array | string | number | true | false | null
    start: int
    end: int                        # exclusive
    members: list = field(default_factory=list)   # object: [(key, key_start, Node)]; array: [Node]


def where(text: str, i: int) -> str:
    line = text.count("\n", 0, i) + 1
    col = i - (text.rfind("\n", 0, i) + 1) + 1
    return f"line {line}, column {col}"


class _Parser:
    def __init__(self, s: str):
        self.s, self.i, self.n = s, 0, len(s)

    def ws(self) -> None:
        s, i, n = self.s, self.i, self.n
        while i < n and s[i] in _WS:
            i += 1
        self.i = i

    def parse(self) -> Node:
        self.ws()
        node = self.value()
        self.ws()
        if self.i != self.n:
            raise JsonDocError(f"there is extra text after the data, at {where(self.s, self.i)}")
        return node

    def value(self) -> Node:
        if self.i >= self.n:
            raise JsonDocError("the file ends in the middle of the data")
        c, a = self.s[self.i], self.i
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c == '"':
            m = _STR.match(self.s, a)
            if not m:
                raise JsonDocError(f"a text value is not closed with \" — at {where(self.s, a)}")
            self.i = m.end()
            return Node("string", a, self.i)
        for word in ("true", "false", "null"):
            if self.s.startswith(word, a):
                self.i = a + len(word)
                return Node(word, a, self.i)
        m = _NUM.match(self.s, a)
        if m and m.end() > a:
            self.i = m.end()
            return Node("number", a, self.i)
        raise JsonDocError(f"unexpected {c!r} at {where(self.s, a)}")

    def obj(self) -> Node:
        node = Node("object", self.i, -1)
        self.i += 1
        self.ws()
        if self.i < self.n and self.s[self.i] == "}":
            self.i += 1
            node.end = self.i
            return node
        while True:
            self.ws()
            ks = self.i
            if ks >= self.n or self.s[ks] != '"':
                raise JsonDocError(f"expected a \"name\" at {where(self.s, ks)}")
            m = _STR.match(self.s, ks)
            if not m:
                raise JsonDocError(f"a name is not closed with \" — at {where(self.s, ks)}")
            key = json.loads(m.group(0))
            self.i = m.end()
            self.ws()
            if self.i >= self.n or self.s[self.i] != ":":
                raise JsonDocError(f"expected ':' after \"{key}\" at {where(self.s, self.i)}")
            self.i += 1
            self.ws()
            node.members.append((key, ks, self.value()))
            self.ws()
            if self.i < self.n and self.s[self.i] == ",":
                self.i += 1
                continue
            if self.i < self.n and self.s[self.i] == "}":
                self.i += 1
                node.end = self.i
                return node
            raise JsonDocError(f"expected ',' or '}}' at {where(self.s, self.i)}")

    def arr(self) -> Node:
        node = Node("array", self.i, -1)
        self.i += 1
        self.ws()
        if self.i < self.n and self.s[self.i] == "]":
            self.i += 1
            node.end = self.i
            return node
        while True:
            self.ws()
            node.members.append(self.value())
            self.ws()
            if self.i < self.n and self.s[self.i] == ",":
                self.i += 1
                continue
            if self.i < self.n and self.s[self.i] == "]":
                self.i += 1
                node.end = self.i
                return node
            raise JsonDocError(f"expected ',' or ']' at {where(self.s, self.i)}")


def split_pointer(pointer) -> list:
    if isinstance(pointer, (list, tuple)):
        return list(pointer)
    p = str(pointer)
    if p in ("", "/"):
        return []
    if not p.startswith("/"):
        raise JsonDocError(f"a pointer starts with '/': {p!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in p[1:].split("/")]


def join_pointer(parts) -> str:
    return "".join("/" + str(x).replace("~", "~0").replace("/", "~1") for x in parts)


class JsonDoc:
    """One JSON file's text, the values in it, and where each value sits."""

    def __init__(self, text: str, bom: bool = False):
        self.text = text
        self.bom = bom
        self._reparse()
        self._detect_style()

    # ---------- loading / saving
    @classmethod
    def from_bytes(cls, data: bytes) -> "JsonDoc":
        bom = data.startswith(BOM)
        raw = data[len(BOM):] if bom else data
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise JsonDocError(f"the file is not UTF-8 text (byte {e.start}); the suite will not edit it") from None
        return cls(text, bom)

    def to_bytes(self) -> bytes:
        return (BOM if self.bom else b"") + self.text.encode("utf-8")

    def _reparse(self) -> None:
        self.root = _Parser(self.text).parse()
        try:
            self.value = json.loads(self.text)
        except json.JSONDecodeError as e:          # the span parser is lenient about control characters; json is not
            raise JsonDocError(f"{e.msg} at {where(self.text, e.pos)}") from None

    def _detect_style(self) -> None:
        t = self.text
        self.nl = "\r\n" if "\r\n" in t else "\n"
        pads = re.findall(r"(?m)^([ \t]+)[\"{\[\]}\-0-9tfn]", t)
        if pads and any("\t" in p for p in pads):
            self.unit = "\t"
        elif pads:
            self.unit = " " * min(len(p) for p in pads)
        else:
            self.unit = "  "
        self.ascii = (not any(ord(ch) > 127 for ch in t)) and bool(re.search(r"\\u[0-9a-fA-F]{4}", t))
        self.key_sep = ":" if re.search(r'"\s*:[^\s]', t) and not re.search(r'"\s*:\s', t) else ": "
        self.item_sep = "," if re.search(r",[^\s]", t) and not re.search(r", ", t) else ", "

    # ---------- reading
    def node(self, pointer) -> Node:
        n = self.root
        trail = []
        for part in split_pointer(pointer):
            trail.append(part)
            if n.kind == "object":
                hit = None
                for k, _ks, v in n.members:          # last duplicate wins, as in json.loads
                    if k == part:
                        hit = v
                if hit is None:
                    raise JsonDocError(f"no field {join_pointer(trail)}")
                n = hit
            elif n.kind == "array":
                try:
                    idx = int(part)
                except ValueError:
                    raise JsonDocError(f"{join_pointer(trail)}: a list is indexed by number") from None
                if not 0 <= idx < len(n.members):
                    raise JsonDocError(f"no item {join_pointer(trail)} (the list has {len(n.members)})")
                n = n.members[idx]
            else:
                raise JsonDocError(f"{join_pointer(trail[:-1]) or '/'} is a single value, not a list or object")
        return n

    def get(self, pointer, default=...):
        v = self.value
        try:
            for part in split_pointer(pointer):
                v = v[int(part)] if isinstance(v, list) else v[part]
        except (KeyError, IndexError, ValueError, TypeError):
            if default is ...:
                raise JsonDocError(f"no field {pointer}") from None
            return default
        return v

    def has(self, pointer) -> bool:
        return self.get(pointer, default=_MISSING) is not _MISSING

    def span_text(self, pointer) -> str:
        n = self.node(pointer)
        return self.text[n.start:n.end]

    # ---------- encoding in this file's own style
    def _pad_at(self, i: int) -> str:
        line_start = self.text.rfind("\n", 0, i) + 1
        m = re.match(r"[ \t]*", self.text[line_start:i])
        return m.group(0) if m else ""

    def encode(self, value, pad: str = "", inline: bool = False) -> str:
        if inline or not isinstance(value, (dict, list)) or not value:
            return json.dumps(value, ensure_ascii=self.ascii, separators=(self.item_sep, self.key_sep))
        s = json.dumps(value, ensure_ascii=self.ascii, indent=self.unit, separators=(",", self.key_sep))
        return (self.nl + pad).join(s.split("\n"))

    def _splice(self, a: int, b: int, rep: str) -> None:
        old = self.text
        self.text = old[:a] + rep + old[b:]
        try:
            self._reparse()
        except JsonDocError:
            self.text = old
            self._reparse()
            raise

    # ---------- editing
    def set(self, pointer, value) -> bool:
        """Replace one value. Returns False (and changes nothing) when the value is already equal."""
        parts = split_pointer(pointer)
        if not parts:
            raise JsonDocError("the whole file cannot be replaced through set(); edit its fields")
        n = self.node(parts)
        if self.get(parts) == value and type(self.get(parts)) is type(value):
            return False
        multiline = "\n" in self.text[n.start:n.end] or (isinstance(value, (dict, list)) and value and "\n" in self.text)
        rep = self.encode(value, self._pad_at(n.start), inline=not multiline)
        self._splice(n.start, n.end, rep)
        return True

    def add(self, pointer, key: str, value) -> bool:
        """Add a member to the object at `pointer` (after its last member, in its siblings' indentation).
        If the key exists, this is set(). Returns True when the text changed."""
        parts = split_pointer(pointer)
        if self.has(parts + [key]):
            return self.set(parts + [key], value)
        obj = self.node(parts)
        if obj.kind != "object":
            raise JsonDocError(f"{join_pointer(parts) or '/'} is not an object; a field cannot be added to it")
        k = json.dumps(key, ensure_ascii=self.ascii)
        if obj.members:
            _lk, lks, lv = obj.members[-1]
            own_line = "\n" in self.text[obj.start:lks]
            if own_line:
                pad = self._pad_at(lks)
                rep = "," + self.nl + pad + k + self.key_sep + self.encode(value, pad)
            else:
                rep = self.item_sep + k + self.key_sep + self.encode(value, inline=True)
            self._splice(lv.end, lv.end, rep)
        else:
            if "\n" in self.text:
                pad = self._pad_at(obj.start)
                mpad = pad + self.unit
                rep = "{" + self.nl + mpad + k + self.key_sep + self.encode(value, mpad) + self.nl + pad + "}"
            else:
                rep = "{" + k + self.key_sep + self.encode(value, inline=True) + "}"
            self._splice(obj.start, obj.end, rep)
        return True

    def append(self, pointer, value) -> None:
        """Append an item to the list at `pointer`, in its siblings' indentation."""
        parts = split_pointer(pointer)
        arr = self.node(parts)
        if arr.kind != "array":
            raise JsonDocError(f"{join_pointer(parts) or '/'} is not a list")
        if arr.members:
            last = arr.members[-1]
            prev_end = arr.members[-2].end if len(arr.members) > 1 else arr.start + 1
            if "\n" in self.text[prev_end:last.start]:
                pad = self._pad_at(last.start)
                rep = "," + self.nl + pad + self.encode(value, pad)
            else:
                rep = self.item_sep + self.encode(value, inline=True)
            self._splice(last.end, last.end, rep)
        else:
            if "\n" in self.text:
                pad = self._pad_at(arr.start)
                ipad = pad + self.unit
                rep = "[" + self.nl + ipad + self.encode(value, ipad) + self.nl + pad + "]"
            else:
                rep = "[" + self.encode(value, inline=True) + "]"
            self._splice(arr.start, arr.end, rep)

    def walk_strings(self):
        """Every string value with its pointer (keys are not included). For search and the round-trip checks."""
        def rec(n: Node, trail: list):
            if n.kind == "string":
                yield join_pointer(trail), n
            elif n.kind == "object":
                for k, _ks, v in n.members:
                    yield from rec(v, trail + [k])
            elif n.kind == "array":
                for i, v in enumerate(n.members):
                    yield from rec(v, trail + [i])
        yield from rec(self.root, [])


_MISSING = object()


class TextDoc:
    """A plain text data file (a lyric sheet, a notes file): bytes in, the same bytes out. Never edited by the suite."""

    def __init__(self, data: bytes):
        self.data = data

    @classmethod
    def from_bytes(cls, data: bytes) -> "TextDoc":
        return cls(data)

    def to_bytes(self) -> bytes:
        return self.data
