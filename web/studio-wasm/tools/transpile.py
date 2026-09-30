"""Songbird's numba kernels, translated to JavaScript from their own source (one source of truth: the
@njit functions in songbird/synth/*.py), typed as numba typed them (kernels/types.json, from
tools/kernel_types.py) where a render has typed them, by usage otherwise.

usage: uv run python web/studio-wasm/tools/transpile.py [--check]
writes web/studio-wasm/kernels/kernels.gen.mjs and kernels/manifest.json ({kernel: {js, ok, why, ret}}).

What it keeps from numba's semantics, so a port is the same arithmetic in the same order (bit for bit where
the kernel uses only + - * / and comparisons; JS numbers are IEEE doubles and nothing fuses a multiply-add):
Python's % and // (floored, CPython's float algorithm), integer powers by numba's unrolled squaring,
min/max as Python picks, int() truncating, range loops that never see the body reassigning their variable,
module constants frozen at translation as numba freezes them at compile time. An array is a descriptor
{d, nd, n0, n1, s0, s1, t}: d a typed array over its first element, strides in elements; integer arrays
live in Float64Arrays and truncate on store. What it can't translate (uint64 generators, complex numbers,
array expressions) it reports; those kernels stay Python (or get a hand port)."""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent.parent
KERNELS = HERE / "kernels"

MATH = {"exp": "Math.exp", "sin": "Math.sin", "cos": "Math.cos", "tan": "Math.tan", "tanh": "Math.tanh",
        "sinh": "Math.sinh", "cosh": "Math.cosh", "sqrt": "Math.sqrt", "log": "Math.log", "log10": "Math.log10",
        "log2": "Math.log2", "log1p": "Math.log1p", "expm1": "Math.expm1", "floor": "Math.floor",
        "ceil": "Math.ceil", "fabs": "Math.abs", "abs": "Math.abs", "arctan": "Math.atan", "atan": "Math.atan",
        "arctan2": "Math.atan2", "atan2": "Math.atan2", "arcsin": "Math.asin", "arccos": "Math.acos",
        "hypot": "Math.hypot", "trunc": "Math.trunc", "sign": "rt.sign", "isfinite": "Number.isFinite",
        "isnan": "Number.isNaN", "copysign": "rt.copysign"}
CONSTS = {"pi": "Math.PI", "e": "Math.E", "inf": "Infinity", "nan": "NaN"}
ALLOC = {"zeros": 0.0, "empty": 0.0, "ones": 1.0}
RESERVED = {"var", "new", "in", "delete", "default", "function", "this", "case", "class", "const", "let",
            "switch", "typeof", "void", "instanceof", "do", "export", "import", "super", "throw", "catch",
            "enum", "arguments", "eval", "static", "yield", "await", "package", "private", "public"}
DTYPES = {"float64": "f8", "int64": "i8", "int32": "i8", "intp": "i8", "bool_": "b1", "bool": "b1", "uint8": "i8",
          "float32": "f4"}


class Unsupported(Exception):
    pass


def js_name(key: str) -> str:
    return "k_" + key.replace(".", "$")


def ident(name: str) -> str:
    return "$" + name if name in RESERVED else name


class Types:
    """numba's types for one kernel: args by parameter name, locals by name (a set: SSA versions)."""

    def __init__(self, spec: dict | None, params: list[str]):
        self.known = bool(spec and spec["signatures"])
        self.vars: dict[str, str] = {}
        self.ret = None
        if self.known:
            sig = spec["signatures"][0]
            self.ret = sig["return"]
            for p, t in zip(params, sig["args"]):
                self.vars[p] = t
            for other in spec["signatures"][1:]:  # the same array in another layout (C and F): any layout
                for p, t in zip(params, other["args"]):
                    if t != self.vars.get(p) and array_info(t) and array_info(self.vars.get(p)):
                        self.vars[p] = re.sub(r", \w\)$", ", A)", self.vars[p])
            for name, ts in sig["locals"].items():
                arr = [t for t in ts if t.startswith("array(")]
                self.vars.setdefault(name, arr[0] if arr else ("float64" if "float64" in ts else ts[0]))

    def get(self, name):
        return self.vars.get(name)


def array_info(t: str):
    """'array(float64, 2d, C)' -> ('f8', 2, 'C')"""
    m = re.match(r"array\((\w+), (\d)d, (\w)\)", t or "")
    if not m:
        return None
    return DTYPES.get(m.group(1), "?" + m.group(1)), int(m.group(2)), m.group(3)


class Kernel:
    def __init__(self, key, fn: ast.FunctionDef, module, names: dict, types: dict, fastmath: bool):
        self.key, self.fn, self.module, self.names, self.fastmath = key, fn, module, names, fastmath
        self.params = [a.arg for a in fn.args.args]
        self.defaults = fn.args.defaults
        self.types = Types(types.get(key), self.params)
        self.arrays: dict[str, tuple] = {}  # name -> (dtype, ndim, layout)
        self.tuples: set[str] = set()
        self.ints: set[str] = set()
        self.tmp = 0
        self.consts: dict[str, str] = {}
        self.calls: set[str] = set()
        self.big: set[str] = set()
        self.global_arrays: dict[str, str] = {}  # name -> module constant  # uint64 scalars: BigInt, wrapped to 64 bits after each op

    # ---------------------------------------------------------------- analysis
    def analyse(self):
        for name, t in self.types.vars.items():
            info = array_info(t)
            if info:
                if info[0].startswith("?"):
                    raise Unsupported(f"{name}: {t}")
                self.arrays[name] = info
            elif t.startswith(("UniTuple", "Tuple")):
                self.tuples.add(name)
            elif t == "uint64":
                self.big.add(name)
            elif re.match(r"u?int\d+|bool", t):
                self.ints.add(name)
            if ("uint64" in t and t != "uint64") or "complex" in t:
                raise Unsupported(f"{name}: {t}")
        if not self.types.known:
            self.guess()
        for node in ast.walk(self.fn):
            if isinstance(node, ast.Call):
                f = ast.unparse(node.func)
                if f in ("complex", "np.complex128") or (f == "np.uint64" and not self.types.known):
                    raise Unsupported(f"calls {f}")

    def guess(self):
        """No numba types (no render played this kernel): arrays by how names are used."""
        fn = self.fn
        two = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                n = node.value.id
                dims = len(node.slice.elts) if isinstance(node.slice, ast.Tuple) else 1
                self.arrays.setdefault(n, ("f8", 1, "A"))
                if dims == 2:
                    two.add(n)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr in ("shape", "copy", "size"):
                self.arrays.setdefault(node.value.id, ("f8", 1, "A"))
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple) \
                    and ast.unparse(node.value).endswith(".shape") and len(node.targets[0].elts) == 2:
                two.add(node.value.value.id)
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
                f = ast.unparse(node.value.func)
                name = node.targets[0].id
                if f.startswith("np.") and f[3:] in (*ALLOC, "full", "empty_like", "zeros_like"):
                    dtype = "f8"
                    for a in node.value.args[1:] + [k.value for k in node.value.keywords if k.arg == "dtype"]:
                        dtype = DTYPES.get(ast.unparse(a).removeprefix("np."), dtype)
                    shape = node.value.args[0] if node.value.args else None
                    self.arrays[name] = (dtype, 2 if isinstance(shape, ast.Tuple) else 1, "C")
                    if isinstance(shape, ast.Tuple):
                        two.add(name)
                    if f[3:] in ("empty_like", "zeros_like") and isinstance(shape, ast.Name):
                        self.arrays[name] = self.arrays.get(shape.id, ("f8", 1, "C"))
        for n in two:
            d, _, lay = self.arrays.get(n, ("f8", 1, "A"))
            self.arrays[n] = (d, 2, lay)
        for node in ast.walk(fn):  # names only ever given ints
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                self.ints.add(node.target.id)

    def is_int(self, e) -> bool:
        if isinstance(e, ast.Constant):
            return isinstance(e.value, (bool, int))
        if isinstance(e, ast.Name):
            return e.id in self.ints
        if isinstance(e, ast.Call):
            f = ast.unparse(e.func)
            return f in ("int", "len", "math.floor", "math.ceil", "round")
        if isinstance(e, ast.BinOp) and not isinstance(e.op, (ast.Div, ast.Pow)):
            return self.is_int(e.left) and self.is_int(e.right)
        if isinstance(e, ast.UnaryOp):
            return self.is_int(e.operand)
        if isinstance(e, ast.Subscript) and ast.unparse(e.value).endswith(".shape"):
            return True
        if isinstance(e, ast.Subscript) and isinstance(e.value, ast.Name) and e.value.id in self.arrays:
            return self.arrays[e.value.id][0] != "f8"
        return False

    # ---------------------------------------------------------------- emit
    def new_tmp(self) -> str:
        self.tmp += 1
        return f"$t{self.tmp}"

    def translate(self) -> str:
        self.analyse()
        body = []
        for s in self.fn.body:
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str):
                continue
            body.extend(self.stmt(s, 1))
        locs = set()
        for node in ast.walk(self.fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                locs.add(node.id)
        locs -= set(self.params)
        decl = sorted(ident(n) for n in locs) + [f"$t{i}" for i in range(1, self.tmp + 1)]
        for n in sorted(self.arrays):
            if n in locs or n in self.params or n in self.global_arrays:
                decl += [f"{n}_d", f"{n}_n0", f"{n}_n1", f"{n}_s0", f"{n}_s1"]
        out = []
        args = []
        for i, p in enumerate(self.params):
            k = len(self.params) - len(self.defaults)
            if i >= k:
                args.append(f"{ident(p)} = {self.expr(self.defaults[i - k])}")
            else:
                args.append(ident(p))
        out.append(f"export function {js_name(self.key)}({', '.join(args)}) {{")
        if decl:
            out.append(f"  let {', '.join(decl)};")
        for n, cname in sorted(self.global_arrays.items()):
            out.append(f"  {n}_d = {cname}.d; {n}_n0 = {cname}.n0; {n}_n1 = {cname}.n1; {n}_s0 = {cname}.s0; {n}_s1 = {cname}.s1;")
        for p in self.params:
            if p in self.arrays:
                out.append("  " + self.unpack(p))
            if p in self.big:
                out.append(f"  {ident(p)} = BigInt({ident(p)});")
        out.extend(body)
        out.append("}")
        return "\n".join(out)

    def unpack(self, n) -> str:
        return f"{n}_d = {n}.d; {n}_n0 = {n}.n0; {n}_n1 = {n}.n1; {n}_s0 = {n}.s0; {n}_s1 = {n}.s1;"

    def stmt(self, s, depth) -> list[str]:
        pad = "  " * depth
        E = self.expr
        if isinstance(s, ast.Assign):
            if len(s.targets) > 1:
                t = self.new_tmp()
                lines = [f"{pad}{t} = {E(s.value)};"]
                for tg in s.targets:
                    lines += self.assign(tg, t, pad, value_node=s.value)
                return lines
            return self.assign(s.targets[0], None, pad, value_node=s.value)
        if isinstance(s, ast.AnnAssign):
            return self.assign(s.target, None, pad, value_node=s.value)
        if isinstance(s, ast.AugAssign):
            op = s.op
            if isinstance(s.target, ast.Name):
                name = ident(s.target.id)
                return [f"{pad}{name} = {self.binop(op, ast.Name(s.target.id, ast.Load()), s.value)};"]
            if isinstance(s.target, ast.Subscript):
                ref = self.element(s.target)
                cur = ast.Subscript(s.target.value, s.target.slice, ast.Load())
                return [f"{pad}{ref} = {self.store_cast(s.target, self.binop(op, cur, s.value))};"]
            raise Unsupported("augassign target")
        if isinstance(s, ast.For):
            return self.for_(s, depth)
        if isinstance(s, ast.While):
            if s.orelse:
                raise Unsupported("while-else")
            lines = [f"{pad}while ({self.truth(s.test)}) {{"]
            for b in s.body:
                lines += self.stmt(b, depth + 1)
            return lines + [f"{pad}}}"]
        if isinstance(s, ast.If):
            lines = [f"{pad}if ({self.truth(s.test)}) {{"]
            for b in s.body:
                lines += self.stmt(b, depth + 1)
            if s.orelse:
                lines.append(f"{pad}}} else {{")
                for b in s.orelse:
                    lines += self.stmt(b, depth + 1)
            return lines + [f"{pad}}}"]
        if isinstance(s, ast.Break):
            return [f"{pad}break;"]
        if isinstance(s, ast.Continue):
            return [f"{pad}continue;"]
        if isinstance(s, ast.Pass):
            return []
        if isinstance(s, ast.Return):
            if s.value is None:
                return [f"{pad}return;"]
            return [f"{pad}return {E(s.value)};"]
        if isinstance(s, ast.Expr):
            if isinstance(s.value, ast.Constant):
                return []
            return [f"{pad}{E(s.value)};"]
        raise Unsupported(type(s).__name__)

    def assign(self, tg, value_js, pad, value_node=None) -> list[str]:
        E = self.expr
        if isinstance(tg, ast.Name):
            v = value_js if value_js is not None else E(value_node)
            n = ident(tg.id)
            line = f"{pad}{n} = {v};"
            if tg.id in self.arrays:
                line += " " + self.unpack(tg.id)
            return [line]
        if isinstance(tg, ast.Tuple):
            # a, b = x.shape / a, b = c, d / a, b = call()
            if value_js is None and isinstance(value_node, ast.Attribute) and value_node.attr == "shape":
                arr = value_node.value.id
                return [f"{pad}{ident(e.id)} = {arr}_n{i};" for i, e in enumerate(tg.elts)]
            if value_js is None and isinstance(value_node, ast.Tuple):
                tmps = [self.new_tmp() for _ in value_node.elts]
                lines = [f"{pad}{t} = {E(v)};" for t, v in zip(tmps, value_node.elts)]
                for e, t in zip(tg.elts, tmps):
                    lines += self.assign(e, t, pad)
                return lines
            t = self.new_tmp()
            lines = [f"{pad}{t} = {value_js if value_js is not None else E(value_node)};"]
            for i, e in enumerate(tg.elts):
                lines += self.assign(e, f"{t}[{i}]", pad)
            return lines
        if isinstance(tg, ast.Subscript):
            if self.has_slice(tg):
                v = value_js if value_js is not None else E(value_node)
                return [f"{pad}rt.setslice({self.slice_view(tg)}, {v});"]
            v = value_js if value_js is not None else E(value_node)
            return [f"{pad}{self.element(tg)} = {self.store_cast(tg, v)};"]
        raise Unsupported(f"assign to {type(tg).__name__}")

    def store_cast(self, tg, v):
        name = tg.value.id if isinstance(tg.value, ast.Name) else None
        if name and self.arrays.get(name, ("f8",))[0] == "i8":
            return f"Math.trunc({v})"
        if name and self.arrays.get(name, ("f8",))[0] == "b1":
            return f"(({v}) ? 1 : 0)"
        return v

    def for_(self, s, depth) -> list[str]:
        pad = "  " * depth
        it = s.iter
        if not (isinstance(it, ast.Call) and ast.unparse(it.func) == "range") or s.orelse:
            raise Unsupported("for over " + ast.unparse(it))
        a = [self.expr(x) for x in it.args]
        start, stop, step = ("0", a[0], "1") if len(a) == 1 else (a[0], a[1], a[2] if len(a) > 2 else "1")
        neg = len(it.args) > 2 and ast.unparse(it.args[2]).startswith("-")
        if not isinstance(s.target, ast.Name):
            raise Unsupported("for target")
        i = self.new_tmp()
        e = self.new_tmp()
        var = ident(s.target.id)
        cmp = ">" if neg else "<"
        if len(it.args) > 2 and not isinstance(it.args[2], (ast.Constant, ast.UnaryOp)):
            st = self.new_tmp()  # a step known only when the loop starts: its sign decides the test
            lines = [f"{pad}for ({i} = {start}, {e} = {stop}, {st} = {step}; ({st} > 0 ? {i} < {e} : {i} > {e}); {i} += {st}) {{",
                     f"{pad}  {var} = {i};"]
        else:
            lines = [f"{pad}for ({i} = {start}, {e} = {stop}; {i} {cmp} {e}; {i} += {step}) {{", f"{pad}  {var} = {i};"]
        for b in s.body:
            lines += self.stmt(b, depth + 1)
        return lines + [f"{pad}}}"]

    def truth(self, e) -> str:
        return self.expr(e)

    # ---------------------------------------------------------------- subscripts
    def has_slice(self, sub) -> bool:
        idx = sub.slice.elts if isinstance(sub.slice, ast.Tuple) else [sub.slice]
        return any(isinstance(i, ast.Slice) for i in idx)

    def indices(self, sub):
        return sub.slice.elts if isinstance(sub.slice, ast.Tuple) else [sub.slice]

    def index(self, name, k, node) -> str:
        """An index into dimension k of array name, wrapped when it is a negative literal (numba wraps)."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return f"({name}_n{k} - {node.operand.value})"
        return self.expr(node)

    def element(self, sub) -> str:
        if not isinstance(sub.value, ast.Name) or sub.value.id not in self.arrays:
            raise Unsupported("subscript of " + ast.unparse(sub.value))
        n = sub.value.id
        _, nd, layout = self.arrays[n]
        idx = self.indices(sub)
        if len(idx) != nd:
            raise Unsupported(f"{len(idx)} indices into a {nd}d array {n}")
        if nd == 1:
            i = self.index(n, 0, idx[0])
            return f"{n}_d[{i}]" if layout == "C" else f"{n}_d[({i}) * {n}_s0]"
        i, j = self.index(n, 0, idx[0]), self.index(n, 1, idx[1])
        if layout == "C":
            return f"{n}_d[({i}) * {n}_s0 + ({j})]"
        return f"{n}_d[({i}) * {n}_s0 + ({j}) * {n}_s1]"

    def slice_view(self, sub) -> str:
        n = sub.value.id
        idx = self.indices(sub)
        _, nd, _ = self.arrays[n]
        if nd == 1 and isinstance(idx[0], ast.Slice):
            sl = idx[0]
            if sl.step is not None:
                raise Unsupported("stepped slice")
            lo = self.expr(sl.lower) if sl.lower is not None else "0"
            hi = self.expr(sl.upper) if sl.upper is not None else f"{n}_n0"
            return f"rt.slice1({n}, {lo}, {hi})"
        if nd == 2 and len(idx) == 2 and not isinstance(idx[0], ast.Slice) and isinstance(idx[1], ast.Slice):
            sl = idx[1]
            lo = self.expr(sl.lower) if sl.lower is not None else "0"
            hi = self.expr(sl.upper) if sl.upper is not None else f"{n}_n1"
            return f"rt.slice1(rt.row({n}, {self.expr(idx[0])}), {lo}, {hi})"
        raise Unsupported("slice " + ast.unparse(sub))

    # ---------------------------------------------------------------- expressions
    def is_big(self, e) -> bool:
        if isinstance(e, ast.Name):
            return e.id in self.big
        if isinstance(e, ast.Call):
            return ast.unparse(e.func) == "np.uint64"
        if isinstance(e, ast.BinOp):
            return (self.is_big(e.left) or self.is_big(e.right)) and not (self.is_floaty(e.left) or self.is_floaty(e.right))
        return False

    def is_floaty(self, e) -> bool:
        if isinstance(e, ast.Constant):
            return isinstance(e.value, float)
        if isinstance(e, ast.Name):
            return (self.types.get(e.id) or "").startswith("float")
        if isinstance(e, ast.BinOp):
            return isinstance(e.op, ast.Div) or self.is_floaty(e.left) or self.is_floaty(e.right)
        if isinstance(e, ast.Subscript) and isinstance(e.value, ast.Name) and e.value.id in self.arrays:
            return self.arrays[e.value.id][0] == "f8"
        if isinstance(e, ast.Call):
            return ast.unparse(e.func).partition(".")[2] in MATH or ast.unparse(e.func) == "float"
        return False

    def big_binop(self, op, l, r) -> str:
        if self.is_floaty(l) or self.is_floaty(r):  # uint64 with a float: numba works in float64
            L = f"Number({self.expr(l)})" if self.is_big(l) else self.expr(l)
            R = f"Number({self.expr(r)})" if self.is_big(r) else self.expr(r)
            ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
            if type(op) not in ops:
                raise Unsupported("uint64 with float " + type(op).__name__)
            return f"({L} {ops[type(op)]} {R})"
        L = self.expr(l) if self.is_big(l) else f"BigInt({self.expr(l)})"
        R = self.expr(r) if self.is_big(r) else f"BigInt({self.expr(r)})"
        wrap = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.LShift: "<<"}
        plain = {ast.RShift: ">>", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^", ast.FloorDiv: "/", ast.Mod: "%"}
        if type(op) in wrap:
            return f"BigInt.asUintN(64, {L} {wrap[type(op)]} {R})"
        if type(op) in plain:
            return f"({L} {plain[type(op)]} {R})"
        if isinstance(op, ast.Div):
            return f"(Number({L}) / Number({R}))"
        raise Unsupported("uint64 " + type(op).__name__)

    def binop(self, op, l, r) -> str:
        if self.is_big(l) or self.is_big(r):
            return self.big_binop(op, l, r)
        L, R = self.expr(l), self.expr(r)
        if isinstance(op, ast.Add):
            return f"({L} + {R})"
        if isinstance(op, ast.Sub):
            return f"({L} - {R})"
        if isinstance(op, ast.Mult):
            return f"({L} * {R})"
        if isinstance(op, ast.Div):
            return f"({L} / {R})"
        if isinstance(op, ast.FloorDiv):
            if self.is_int(l) and self.is_int(r):
                return f"Math.floor({L} / {R})"
            return f"rt.floordiv({L}, {R})"
        if isinstance(op, ast.Mod):
            return f"rt.mod({L}, {R})"
        if isinstance(op, ast.Pow):
            c = r.value if isinstance(r, ast.Constant) else None
            if isinstance(r, ast.UnaryOp) and isinstance(r.op, ast.USub) and isinstance(r.operand, ast.Constant):
                c = -r.operand.value
            if isinstance(c, int) and not isinstance(c, bool):
                return f"rt.ipow({L}, {c})"  # numba's unrolled squaring for a literal integer power
            if isinstance(c, float) and c == 2.0:
                return f"rt.ipow({L}, 2)"  # LLVM turns pow(x, 2.0) into x * x
            if self.is_int(r) and not isinstance(r, ast.Constant):
                return f"rt.ipowv({L}, {R})"
            return f"Math.pow({L}, {R})"
        if isinstance(op, ast.BitAnd):
            return f"({L} & {R})"
        if isinstance(op, ast.BitOr):
            return f"({L} | {R})"
        if isinstance(op, ast.BitXor):
            return f"({L} ^ {R})"
        if isinstance(op, ast.RShift):
            return f"({L} >> {R})"
        if isinstance(op, ast.LShift):
            return f"({L} << {R})"
        raise Unsupported(type(op).__name__)

    def expr(self, e) -> str:
        E = self.expr
        if isinstance(e, ast.Constant):
            v = e.value
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, int):
                return str(v)
            if isinstance(v, float):
                if v != v:
                    return "NaN"
                if v in (float("inf"), float("-inf")):
                    return "Infinity" if v > 0 else "(-Infinity)"
                return repr(v)
            if v is None:
                return "undefined"
            raise Unsupported(f"constant {v!r}")
        if isinstance(e, ast.Name):
            if e.id in ("True", "False"):
                return e.id.lower()
            return self.name(e.id)
        if isinstance(e, ast.BinOp):
            if self.is_array_expr(e):  # arrays, elementwise (1.0 / dts)
                return self.vector(e)
            return self.binop(e.op, e.left, e.right)
        if isinstance(e, ast.UnaryOp):
            if isinstance(e.op, ast.USub):
                return f"(- {E(e.operand)})"
            if isinstance(e.op, ast.UAdd):
                return E(e.operand)
            if isinstance(e.op, ast.Not):
                return f"(!{E(e.operand)})"
            if isinstance(e.op, ast.Invert):
                return f"(~{E(e.operand)})"
        if isinstance(e, ast.BoolOp):
            op = " && " if isinstance(e.op, ast.And) else " || "
            return "(" + op.join(E(v) for v in e.values) + ")"
        if isinstance(e, ast.Compare):
            ops = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "===", ast.NotEq: "!=="}
            parts, left = [], e.left
            for op, right in zip(e.ops, e.comparators):
                if type(op) not in ops:
                    raise Unsupported(type(op).__name__)
                o = ops[type(op)]
                if (self.is_big(left) or self.is_big(right)) and o in ("===", "!=="):
                    o = o[:-1]  # BigInt == Number compares values
                parts.append(f"({E(left)} {o} {E(right)})")
                left = right
            return "(" + " && ".join(parts) + ")"
        if isinstance(e, ast.IfExp):
            return f"({E(e.test)} ? {E(e.body)} : {E(e.orelse)})"
        if isinstance(e, ast.Tuple):
            return "[" + ", ".join(E(x) for x in e.elts) + "]"
        if isinstance(e, ast.Subscript):
            if isinstance(e.value, ast.Attribute) and e.value.attr == "shape":
                arr = e.value.value.id
                k = e.slice.value if isinstance(e.slice, ast.Constant) else None
                if k is None:
                    raise Unsupported("shape index")
                return f"{arr}_n{k}"
            if isinstance(e.value, ast.Name) and e.value.id not in self.arrays:
                n = e.value.id
                if n in self.tuples or (n not in self.params and not self.is_local(n)
                                        and self.global_value(n) is not None and n not in self.arrays):
                    return f"{E(e.value)}[{E(e.slice)}]"  # a tuple (a JS array), not an ndarray
            if self.has_slice(e):
                return self.slice_view(e)
            n = e.value.id if isinstance(e.value, ast.Name) else None
            if n in self.arrays and self.arrays[n][1] == 2 and len(self.indices(e)) == 1:
                return f"rt.row({n}, {E(e.slice)})"
            return self.element(e)
        if isinstance(e, ast.Attribute):
            base = ast.unparse(e.value)
            if base in ("np", "math", "numpy") and e.attr in CONSTS:
                return CONSTS[e.attr]
            if e.attr == "size" and isinstance(e.value, ast.Name):
                n = e.value.id
                return f"{n}_n0" if self.arrays[n][1] == 1 else f"({n}_n0 * {n}_n1)"
            if e.attr == "ndim":
                return str(self.arrays[e.value.id][1])
            if base in ("np", "numpy") and e.attr in DTYPES:  # a dtype given by position (np.empty(n, np.int64))
                return f"'{DTYPES[e.attr]}'"
            raise Unsupported("attribute " + ast.unparse(e))
        if isinstance(e, ast.Call):
            return self.call(e)
        raise Unsupported(type(e).__name__)

    def name(self, n) -> str:
        if n in self.params or self.is_local(n):
            return ident(n)
        v = self.global_value(n)
        if v is None:
            raise Unsupported(f"global {n}")
        return v

    def is_local(self, n) -> bool:
        for node in ast.walk(self.fn):
            if isinstance(node, ast.Name) and node.id == n and isinstance(node.ctx, ast.Store):
                return True
        return False

    def global_value(self, n):
        """A module global, frozen as numba freezes it: a number inline, an array as a module constant."""
        import numpy as np

        if n in self.consts:
            return self.consts[n]
        if not hasattr(self.module, n):
            return None
        v = getattr(self.module, n)
        if isinstance(v, bool):
            js = "true" if v else "false"
        elif isinstance(v, (int, float, np.integer, np.floating)):
            js = self.expr(ast.Constant(float(v) if isinstance(v, (float, np.floating)) else int(v)))
        elif isinstance(v, np.ndarray) and v.dtype.kind in "fiub" and v.ndim <= 2:
            cname = f"C_{self.key.replace('.', '$')}_{n}"
            data = ", ".join(repr(float(x)) for x in v.ravel())
            nd = v.ndim
            n1 = v.shape[1] if nd == 2 else 0
            MODULE_CONSTS[cname] = (f"const {cname} = rt.array([{data}], {nd}, {v.shape[0]}, {n1}, "
                                    f"'{'f8' if v.dtype.kind == 'f' else 'i8'}');")
            self.arrays[n] = ("f8" if v.dtype.kind == "f" else "i8", nd, "C")
            self.global_arrays[n] = cname
            js = cname
        elif isinstance(v, tuple) and all(isinstance(x, (int, float)) for x in v):
            js = "[" + ", ".join(self.expr(ast.Constant(x)) for x in v) + "]"
        else:
            return None
        self.consts[n] = js
        return js

    def kernel_ref(self, f: str):
        """A call to another kernel: in this module, or imported (from .osc import _blep; osc._edges)."""
        if "." not in f:
            key = self.names.get(f)
            if key is None and f"{self.key.rsplit('.', 1)[0]}.{f}" in ALL:
                key = f"{self.key.rsplit('.', 1)[0]}.{f}"
        else:
            mod, attr = f.split(".", 1)
            key = f"{self.names[mod]}.{attr}" if mod in self.names else None
        return key if key in ALL else None

    def call(self, e) -> str:
        E = self.expr
        f = ast.unparse(e.func)
        args = [E(a) for a in e.args]
        if e.keywords and not f.startswith("np."):
            raise Unsupported(f"keywords in {f}")
        key = self.kernel_ref(f)
        if key is not None:
            self.calls.add(key)
            return f"{js_name(key)}({', '.join(args)})"
        if f in ("int",):
            return f"Math.trunc({args[0]})"
        if f == "float":
            return f"Number({args[0]})" if self.is_big(e.args[0]) else f"(+{args[0]})"
        if f == "np.uint64":
            a = e.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, int):
                return f"{a.value}n"
            return f"BigInt.asUintN(64, BigInt({args[0]}))"
        if f == "bool":
            return f"(!!{args[0]})"
        if f == "abs":
            return f"Math.abs({args[0]})"
        if f in ("min", "max"):
            if len(args) == 1:
                raise Unsupported(f"{f} of a sequence")
            return f"rt.{'pmin' if f == 'min' else 'pmax'}({', '.join(args)})"
        if f == "len":
            a = e.args[0]
            if isinstance(a, ast.Name) and a.id in self.arrays:
                return f"{a.id}_n0"
            raise Unsupported("len of " + ast.unparse(a))
        if f == "round":
            return f"rt.pyround({args[0]})"
        mod, _, attr = f.partition(".")
        if mod in ("np", "numpy") and (attr in MATH or attr in ("minimum", "maximum")) \
                and any(self.is_array_expr(a) for a in e.args):
            return self.vector(e)
        if mod in ("np", "math", "numpy") and attr in MATH:
            return f"{MATH[attr]}({', '.join(args)})"
        if mod in ("np", "numpy") and attr in ("minimum", "maximum"):
            return f"rt.{'pmin' if attr == 'minimum' else 'pmax'}({', '.join(args)})"
        if mod in ("np", "numpy") and attr in (*ALLOC, "full", "empty_like", "zeros_like"):
            dtype = "f8"
            extra = e.args[1:] if attr != "full" else e.args[2:]
            for a in list(extra) + [k.value for k in e.keywords if k.arg == "dtype"]:
                d = DTYPES.get(ast.unparse(a).removeprefix("np.").removeprefix("numpy."))
                if d is None:
                    raise Unsupported(f"dtype {ast.unparse(a)}")
                dtype = d
            if attr in ("empty_like", "zeros_like"):
                src = e.args[0]
                if not (isinstance(src, ast.Name) and src.id in self.arrays):
                    raise Unsupported(f"{f} of {ast.unparse(src)}")
                n = src.id
                return f"rt.alloc({self.arrays[n][1]}, {n}_n0, {n}_n1, '{self.arrays[n][0]}', 0)"
            shape = e.args[0]
            fill = "0" if attr != "ones" else "1"
            if attr == "full":
                fill = args[1]
            if isinstance(shape, ast.Tuple):
                if len(shape.elts) != 2:
                    raise Unsupported("3d array")
                return f"rt.alloc(2, {E(shape.elts[0])}, {E(shape.elts[1])}, '{dtype}', {fill})"
            return f"rt.alloc(1, {E(shape)}, 0, '{dtype}', {fill})"
        if isinstance(e.func, ast.Attribute) and e.func.attr == "copy" and not e.args:
            return f"rt.copy({E(e.func.value)})"
        if isinstance(e.func, ast.Attribute) and e.func.attr in ("reshape", "ravel") \
                and isinstance(e.func.value, ast.Name) and e.func.value.id in self.arrays:
            # x.reshape(-1) (or to its size), x.ravel(): numba's, a view of a contiguous array (rt.flat)
            if e.func.attr == "reshape" and (len(e.args) != 1 or ast.unparse(e.args[0]) != "-1"):
                raise Unsupported("reshape " + ast.unparse(e))
            return f"rt.flat({E(e.func.value)})"
        if f in ("np.float64", "float64"):
            return f"(+{args[0]})"
        if f in ("np.int64", "np.intp", "np.int32"):
            return f"Math.trunc({args[0]})"
        raise Unsupported(f"call {f}")

    def vector(self, e) -> str:
        """A numpy expression over 1-d arrays (np.cos(2 * np.pi * freqs / sr), np.minimum(a / sr, 0.25)), as
        numba's ufunc loops work it out: element by element, the same scalar operations."""
        length = self.vector_length(e)
        return f"rt.vec({length}, ($i) => {self.elem(e)})"

    def vector_length(self, e) -> str:
        for node in ast.walk(e):
            if isinstance(node, ast.Name) and node.id in self.arrays and self.arrays[node.id][1] == 1:
                return f"{node.id}_n0"
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in self.arrays \
                    and self.arrays[node.value.id][1] == 2 and len(self.indices(node)) == 1:
                return f"{node.value.id}_n1"
        raise Unsupported("array expression " + ast.unparse(e))

    def elem(self, e) -> str:
        if isinstance(e, ast.Name) and e.id in self.arrays:
            if self.arrays[e.id][1] != 1:
                raise Unsupported("2d array expression")
            return f"{e.id}_d[$i * {e.id}_s0]"
        if isinstance(e, ast.Subscript) and isinstance(e.value, ast.Name) and e.value.id in self.arrays \
                and self.arrays[e.value.id][1] == 2 and len(self.indices(e)) == 1:
            n = e.value.id
            return f"{n}_d[({self.expr(e.slice)}) * {n}_s0 + $i * {n}_s1]"
        if isinstance(e, ast.BinOp) and self.is_array_expr(e):
            ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
            if type(e.op) not in ops:
                raise Unsupported("array " + type(e.op).__name__)
            return f"({self.elem(e.left)} {ops[type(e.op)]} {self.elem(e.right)})"
        if isinstance(e, ast.Call) and any(self.is_array_expr(a) for a in e.args):
            f = ast.unparse(e.func)
            attr = f.partition(".")[2]
            inner = ", ".join(self.elem(a) for a in e.args)
            if attr in MATH:
                return f"{MATH[attr]}({inner})"
            if attr in ("minimum", "maximum"):  # numpy's: NaN wins; otherwise the lesser (greater)
                return f"rt.{'npmin' if attr == 'minimum' else 'npmax'}({inner})"
            raise Unsupported("array call " + f)
        return self.expr(e)

    def is_array_expr(self, a) -> bool:
        if isinstance(a, ast.Name):
            return a.id in self.arrays
        if isinstance(a, ast.Subscript):
            return self.has_slice(a) or (isinstance(a.value, ast.Name) and a.value.id in self.arrays
                                         and len(self.indices(a)) < self.arrays[a.value.id][1])
        if isinstance(a, ast.BinOp):
            return self.is_array_expr(a.left) or self.is_array_expr(a.right)
        if isinstance(a, ast.Call):
            f = ast.unparse(a.func)
            if f.startswith(("np.", "numpy.")) and f.partition(".")[2] in (*MATH, "minimum", "maximum"):
                return any(self.is_array_expr(x) for x in a.args)
        return False


ALL: dict[str, tuple] = {}
HAND = ("synth.piano._spectrum", "synth.struck._bank")  # complex numbers: ported by hand, kernels/hand.mjs
MODULE_CONSTS: dict[str, str] = {}


def collect():
    """Every @njit function in songbird/, with the names its module imports kernels by."""
    for path in sorted((ROOT / "songbird").rglob("*.py")):
        tree = ast.parse(path.read_text())
        modname = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        key_mod = modname.removeprefix("songbird.")
        names = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level >= 1:
                pkg = modname.rsplit(".", node.level)[0]
                src = f"{pkg}.{node.module}" if node.module else pkg
                for a in node.names:
                    if node.module:
                        names[a.asname or a.name] = f"{src.removeprefix('songbird.')}.{a.name}"
                    else:
                        names[a.asname or a.name] = f"{src.removeprefix('songbird.')}.{a.name}"
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and any("njit" in ast.unparse(d) for d in node.decorator_list):
                fastmath = any("fastmath=True" in ast.unparse(d) for d in node.decorator_list)
                ALL[f"{key_mod}.{node.name}"] = (node, modname, names, fastmath, path)


def main():
    sys.path.insert(0, str(ROOT))
    collect()
    types = json.loads((KERNELS / "types.json").read_text()) if (KERNELS / "types.json").exists() else {}
    manifest, chunks = {}, []
    # names a module imports kernels by map to kernel keys (from .osc import _blep -> synth.osc._blep)
    for key, (fn, modname, names, fastmath, path) in ALL.items():
        module = importlib.import_module(modname)
        k = Kernel(key, fn, module, {n: v for n, v in names.items()}, types, fastmath)
        if key in HAND:
            arrays = {p: array_info(k.types.get(p)) for p in k.params if array_info(k.types.get(p) or "")}
            manifest[key] = {"js": js_name(key), "ok": True, "typed": k.types.known, "ret": k.types.ret,
                             "params": k.params, "arrays": arrays, "fastmath": fastmath, "calls": [], "hand": True}
            continue
        try:
            src = k.translate()
            chunks.append(f"// {path.relative_to(ROOT)}:{fn.lineno}{'  (fastmath in numba)' if fastmath else ''}\n{src}\n")
            manifest[key] = {"js": js_name(key), "ok": True, "typed": k.types.known, "ret": k.types.ret,
                             "params": k.params, "arrays": {p: k.arrays[p] for p in k.params if p in k.arrays},
                             "fastmath": fastmath, "calls": sorted(k.calls)}
        except Unsupported as err:
            manifest[key] = {"js": None, "ok": False, "why": str(err), "typed": k.types.known, "fastmath": fastmath}
    # a kernel calling one that failed fails too
    changed = True
    while changed:
        changed = False
        for key, m in manifest.items():
            if m["ok"] and any(not manifest[c]["ok"] for c in m["calls"]):
                m["ok"], m["why"] = False, "calls " + ", ".join(c for c in m["calls"] if not manifest[c]["ok"])
                changed = True
    ok = {m["js"] for m in manifest.values() if m["ok"]}
    kept = [c for c in chunks if re.search(r"export function (\S+)\(", c).group(1) in ok]
    head = ("// Generated by web/studio-wasm/tools/transpile.py from songbird's @njit kernels. Do not edit.\n"
            "import * as rt from './rt.mjs';\nexport * from './hand.mjs';\n")
    (KERNELS / "kernels.gen.mjs").write_text(head + "\n".join(MODULE_CONSTS.values()) + "\n\n" + "\n".join(kept))
    (KERNELS / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    good = sum(m["ok"] for m in manifest.values())
    hand = sum(bool(m.get("hand")) for m in manifest.values())
    print(f"{good - hand}/{len(manifest)} kernels translated, {hand} ported by hand (kernels/hand.mjs)")
    for key, m in manifest.items():
        if not m["ok"]:
            print(f"  {key}: {m['why']}")


if __name__ == "__main__":
    main()
