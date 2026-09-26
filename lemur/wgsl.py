"""Build-time analysis of the WGSL behind a ``!compute`` block.

The deck's player needs to know, before it runs anything, which storage
buffers to create (and how large), which compute kernels to dispatch (in which
order, how many workgroups, whether once or every tick), and that there is a
``mainImage`` to draw with. All of that is in the WGSL source itself; this
module reads it out, so a mistake is reported when the deck is built, with a
line number, rather than as a blank slide in front of an audience.

What it understands (a subset of WGSL, enough for declarations):

* ``const NAME = <integer expression>;`` — usable in array sizes and annotations;
* ``struct`` declarations (with ``@align``/``@size``), for sizes;
* ``@group(0) @binding(k) var<storage[, read|read_write]> name: T;`` with a
  fixed-size ``T`` (bindings from 1: binding 0 is lemur's ``lmr`` uniform);
* ``@compute @workgroup_size(x[, y[, z]]) fn name(`` entry points, each preceded
  by ``//! threads X [Y [Z]]`` (and optionally ``//! once``);
* ``fn mainImage(`` — the picture.

``#include "file.wgsl"`` lines are resolved (relative to the including file,
each file once), and every output line remembers where it came from.
"""

from __future__ import annotations

import ast as _pyast
import os
import re
from dataclasses import dataclass, field

__all__ = ["WGSLError", "Buffer", "Kernel", "Program", "read_source", "analyse", "PRELUDE", "TAIL"]

#: What the player adds in front of the author's WGSL (keep in step with
#: ``assets/svg/compute.js``, which uses the same text and its line count).
PRELUDE = """struct Lemur {
  mouse: vec4f, resolution: vec2f, time: f32, dt: f32,
  step: f32, steps: f32, step_raw: u32, frame: u32, tick: u32, seed: u32,
}
@group(0) @binding(0) var<uniform> lmr: Lemur;
fn lmr_hash(x: u32) -> u32 {
  let s = x * 747796405u + 2891336453u;
  let w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
  return (w >> 22u) ^ w;
}
fn lmr_rand(x: u32) -> f32 { return f32(lmr_hash(x)) / 4294967296.0; }
"""

#: … and after it: a full-screen triangle whose fragments call ``mainImage``
#: with Shadertoy's pixel coordinates (origin bottom-left).
TAIL = """
@vertex fn lmr_vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
@fragment fn lmr_fs(@builtin(position) p: vec4f) -> @location(0) vec4f {
  let c = mainImage(vec2f(p.x, lmr.resolution.y - p.y));
  return vec4f(c.rgb, 1.0);
}
"""

MAX_BUFFERS = 7          # WebGPU guarantees 8 storage buffers per stage; one binding is lmr's
MAX_BUFFER_BYTES = 128 * 1024 * 1024


class WGSLError(ValueError):
    """A problem in the WGSL, at ``line`` (1-based, in the expanded source)."""

    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.line = line


@dataclass
class Buffer:
    name: str
    binding: int
    size: int                 # bytes
    access: str               # "read" | "read_write"
    type: str


@dataclass
class Kernel:
    name: str
    workgroup: tuple          # (x, y, z)
    threads: tuple            # (x, y, z)
    once: bool
    line: int

    @property
    def groups(self) -> tuple:
        return tuple(-(-t // w) for t, w in zip(self.threads, self.workgroup))


@dataclass
class Program:
    source: str
    lines: list               # [(file, line)] for every line of ``source``
    buffers: list = field(default_factory=list)
    kernels: list = field(default_factory=list)

    def manifest(self) -> dict:
        """The JSON the player reads (with a compact line map for error messages)."""
        files: list = []
        runs: list = []           # [file index, first source line, count]
        for f, ln in self.lines:
            if f not in files:
                files.append(f)
            fi = files.index(f)
            if runs and runs[-1][0] == fi and runs[-1][1] + runs[-1][2] == ln:
                runs[-1][2] += 1
            else:
                runs.append([fi, ln, 1])
        return {
            "buffers": [{"name": b.name, "binding": b.binding, "size": b.size, "access": b.access}
                        for b in self.buffers],
            "kernels": [{"name": k.name, "groups": list(k.groups), "once": k.once} for k in self.kernels],
            "files": [os.path.basename(f) for f in files],
            "lines": runs,
        }


# -- sources ------------------------------------------------------------------------

def read_source(path: str, seen=None) -> "tuple[str, list]":
    """``path`` with its ``#include "file"`` lines resolved; returns the text and,
    per line, ``(file, line)`` where it came from."""
    seen = set() if seen is None else seen
    path = os.path.abspath(path)
    if path in seen:
        return "", []
    seen.add(path)
    text: list = []
    where: list = []
    with open(path, encoding="utf-8") as fh:
        for n, ln in enumerate(fh.read().splitlines(), start=1):
            m = re.match(r'\s*#\s*include\s+"([^"]+)"', ln)
            if m:
                sub, subw = read_source(os.path.join(os.path.dirname(path), m.group(1)), seen)
                if sub:
                    text.extend(sub.split("\n"))
                    where.extend(subw)
            else:
                text.append(ln)
                where.append((path, n))
    return "\n".join(text), where


# -- types --------------------------------------------------------------------------

_SCALARS = {"f32": (4, 4), "i32": (4, 4), "u32": (4, 4), "f16": (2, 2)}
_SHORT = {"f": "f32", "i": "i32", "u": "u32", "h": "f16"}


def _round(n: int, a: int) -> int:
    return -(-n // a) * a


def _split_args(s: str) -> list:
    """Top-level comma split of a template argument list."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class _Types:
    def __init__(self, consts: dict, structs: dict):
        self.consts = consts
        self.structs = structs            # name -> [(member, type, align_override, size_override)]

    def layout(self, t: str, line: int) -> "tuple[int, int]":
        """(size, alignment) of a host-shareable WGSL type, per the WGSL memory layout rules."""
        t = t.strip()
        if t in _SCALARS:
            return _SCALARS[t]
        m = re.fullmatch(r"vec([234])([fihu])", t)
        if m:
            t = f"vec{m.group(1)}<{_SHORT[m.group(2)]}>"
        m = re.fullmatch(r"mat([234])x([234])([fh])", t)
        if m:
            t = f"mat{m.group(1)}x{m.group(2)}<{_SHORT[m.group(3)]}>"
        m = re.fullmatch(r"vec([234])\s*<\s*(\w+)\s*>", t)
        if m:
            n, (s, _a) = int(m.group(1)), self.layout(m.group(2), line)
            size = n * s
            return size, (2 * s if n == 2 else 4 * s)
        m = re.fullmatch(r"mat([234])x([234])\s*<\s*(\w+)\s*>", t)
        if m:
            c, r = int(m.group(1)), int(m.group(2))
            col_size, col_align = self.layout(f"vec{r}<{m.group(3)}>", line)
            return c * _round(col_size, col_align), col_align
        m = re.fullmatch(r"atomic\s*<\s*(\w+)\s*>", t)
        if m:
            if m.group(1) not in ("u32", "i32"):
                raise WGSLError(f"atomic<{m.group(1)}>: atomics are u32 or i32", line)
            return 4, 4
        m = re.fullmatch(r"array\s*<(.*)>", t, re.S)
        if m:
            args = _split_args(m.group(1))
            if len(args) != 2:
                raise WGSLError(f"'{t}' has no size: give the array a fixed length, "
                                f"e.g. array<f32, 1024> (or a const)", line)
            es, ea = self.layout(args[0], line)
            n = self.eval_int(args[1], line)
            if n <= 0:
                raise WGSLError(f"'{t}': the length must be positive", line)
            return n * _round(es, ea), ea
        if t in self.structs:
            off, align = 0, 1
            for _name, mt, a_over, s_over in self.structs[t]:
                ms, ma = self.layout(mt, line)
                ma = a_over or ma
                ms = s_over or ms
                off = _round(off, ma) + ms
                align = max(align, ma)
            return _round(off, align), align
        if t == "bool":
            raise WGSLError("bool cannot be stored in a buffer: use u32", line)
        raise WGSLError(f"unknown type '{t}' in a buffer declaration", line)

    def eval_int(self, expr: str, line: int) -> int:
        """An integer expression over literals (``256u``, ``0x100``) and integer consts."""
        e = re.sub(r"\b(0x[0-9a-fA-F]+|\d+)[iu]\b", r"\1", expr.strip())
        try:
            tree = _pyast.parse(e, mode="eval")
        except SyntaxError:
            raise WGSLError(f"cannot evaluate '{expr}' (use integers and consts)", line) from None

        def ev(n):
            if isinstance(n, _pyast.Expression):
                return ev(n.body)
            if isinstance(n, _pyast.Constant) and isinstance(n.value, int):
                return n.value
            if isinstance(n, _pyast.Name) and n.id in self.consts:
                return self.consts[n.id]
            if isinstance(n, _pyast.BinOp) and isinstance(n.op, (_pyast.Add, _pyast.Sub, _pyast.Mult,
                                                                    _pyast.FloorDiv, _pyast.Div,
                                                                    _pyast.LShift, _pyast.RShift)):
                a, b = ev(n.left), ev(n.right)
                op = type(n.op)
                return {_pyast.Add: a + b, _pyast.Sub: a - b, _pyast.Mult: a * b,
                        _pyast.FloorDiv: a // b if b else 0, _pyast.Div: a // b if b else 0,
                        _pyast.LShift: a << b, _pyast.RShift: a >> b}[op]
            if isinstance(n, _pyast.UnaryOp) and isinstance(n.op, _pyast.USub):
                return -ev(n.operand)
            raise WGSLError(f"cannot evaluate '{expr}' (use integers and consts)", line)

        return int(ev(tree))


# -- analysis -----------------------------------------------------------------------

def _strip_comments(src: str) -> str:
    """Comments replaced by spaces (so offsets and line numbers stay put);
    ``//!`` annotations are removed too — they are read separately."""
    out = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append("".join(c if c == "\n" else " " for c in src[i:j]))
            i = j
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def analyse(source: str, lines: "list | None" = None) -> Program:
    """Read the buffers and kernels out of ``source`` (see the module doc)."""
    lines = lines or [("<wgsl>", i + 1) for i in range(source.count("\n") + 1)]
    code = _strip_comments(source)

    consts: dict = {}
    types = _Types(consts, {})
    for m in re.finditer(r"\bconst\s+(\w+)\s*(?::\s*\w+\s*)?=\s*([^;]+);", code):
        try:
            consts[m.group(1)] = types.eval_int(m.group(2), _line_of(code, m.start()))
        except WGSLError:
            pass                                  # a float or vector const: not a size

    for m in re.finditer(r"\bstruct\s+(\w+)\s*\{([^}]*)\}", code):
        members = []
        for part in _split_args(m.group(2).replace("\n", " ")):
            part = part.strip().rstrip(",")
            if not part:
                continue
            a_over = re.search(r"@align\s*\(\s*([^)]+)\)", part)
            s_over = re.search(r"@size\s*\(\s*([^)]+)\)", part)
            bare = re.sub(r"@\w+\s*(\([^)]*\))?", "", part).strip()
            mm = re.match(r"(\w+)\s*:\s*(.+)$", bare)
            if not mm:
                continue
            ln = _line_of(code, m.start())
            members.append((mm.group(1), mm.group(2).strip(),
                            types.eval_int(a_over.group(1), ln) if a_over else None,
                            types.eval_int(s_over.group(1), ln) if s_over else None))
        types.structs[m.group(1)] = members

    prog = Program(source=source, lines=lines)
    seen_bindings: dict = {}
    var_re = re.compile(r"((?:@\w+\s*\([^)]*\)\s*)+)var\s*<\s*(\w+)\s*(?:,\s*(\w+)\s*)?>\s*(\w+)\s*:\s*([^;]+);")
    for m in var_re.finditer(code):
        ln = _line_of(code, m.start())
        attrs = dict(re.findall(r"@(\w+)\s*\(\s*([^)]+?)\s*\)", m.group(1)))
        space, access, name, typ = m.group(2), m.group(3) or "read", m.group(4), m.group(5).strip()
        if space == "uniform":
            raise WGSLError(f"'{name}': lemur provides the only uniform, 'lmr' (binding 0); "
                            f"put your data in a storage buffer", ln)
        if space != "storage":
            continue
        group = types.eval_int(attrs.get("group", "0"), ln)
        if group != 0:
            raise WGSLError(f"'{name}': use @group(0) (lemur binds one group)", ln)
        if "binding" not in attrs:
            raise WGSLError(f"'{name}': a storage buffer needs @binding(n)", ln)
        binding = types.eval_int(attrs["binding"], ln)
        if binding == 0:
            raise WGSLError(f"'{name}': binding 0 is lemur's 'lmr' uniform; start at @binding(1)", ln)
        if binding in seen_bindings:
            raise WGSLError(f"'{name}': binding {binding} is already used by '{seen_bindings[binding]}'", ln)
        if access not in ("read", "read_write"):
            raise WGSLError(f"'{name}': access must be read or read_write", ln)
        size, _a = types.layout(typ, ln)
        if size > MAX_BUFFER_BYTES:
            raise WGSLError(f"'{name}' is {size / 2**20:.0f} MiB; buffers are limited to "
                            f"{MAX_BUFFER_BYTES // 2**20} MiB", ln)
        seen_bindings[binding] = name
        prog.buffers.append(Buffer(name, binding, _round(size, 4), access, typ))
    if len(prog.buffers) > MAX_BUFFERS:
        raise WGSLError(f"{len(prog.buffers)} storage buffers; at most {MAX_BUFFERS} are available", 0)
    prog.buffers.sort(key=lambda b: b.binding)

    # annotations: `//! …` lines apply to the next @compute entry point
    pending: list = []
    notes_at: dict = {}
    for i, raw in enumerate(source.split("\n"), start=1):
        s = raw.strip()
        if s.startswith("//!"):
            pending.append((i, s[3:].strip()))
        elif "@compute" in _strip_comments(raw):
            notes_at[i] = pending
            pending = []
    kre = re.compile(r"@compute\b(.*?)\bfn\s+(\w+)\s*\(", re.S)
    for m in kre.finditer(code):
        ln = _line_of(code, m.start())
        name = m.group(2)
        wg = re.search(r"@workgroup_size\s*\(([^)]*)\)", m.group(1))
        if not wg:
            raise WGSLError(f"kernel '{name}' needs @workgroup_size(…)", ln)
        wsz = [types.eval_int(a, ln) for a in _split_args(wg.group(1))]
        wsz = tuple((wsz + [1, 1, 1])[:3])
        threads, once = None, False
        for nl, note in notes_at.get(ln, []):
            word, _, rest = note.partition(" ")
            if word == "threads":
                vals = [types.eval_int(v, nl) for v in rest.split()] if rest.strip() else []
                if not 1 <= len(vals) <= 3 or any(v <= 0 for v in vals):
                    raise WGSLError(f"'//! threads' takes one to three positive counts, e.g. "
                                    f"'//! threads 65536' or '//! threads W H'", nl)
                threads = tuple((vals + [1, 1, 1])[:3])
            elif word == "once":
                once = True
            else:
                raise WGSLError(f"unknown annotation '//! {note}' (known: threads, once)", nl)
        if threads is None:
            raise WGSLError(f"kernel '{name}': say how many threads to run with a "
                            f"'//! threads N' line above it", ln)
        k = Kernel(name, wsz, threads, once, ln)
        if any(g > 65535 for g in k.groups):
            raise WGSLError(f"kernel '{name}': {k.groups} workgroups; at most 65535 per dimension "
                            f"(use a larger @workgroup_size or 2-D threads)", ln)
        prog.kernels.append(k)
    if not re.search(r"\bfn\s+mainImage\s*\(", code):
        raise WGSLError("no 'fn mainImage(fragCoord: vec2f) -> vec4f': it draws the picture", 0)
    return prog
