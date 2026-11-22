"""Native checker contracts."""

import _cxx
import _scratch

import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ENGINE = os.path.join(HERE, "..", "engine")
ROOT = os.path.realpath(os.path.join(HERE, ".."))
BIN = _cxx.BIN
TMP = _scratch.mkdtemp(prefix="brat-check-")

def cxx(path):
    r = subprocess.run([BIN, "check", path], capture_output=True, text=True, encoding="utf-8", timeout=120)
    # 2 is a load error: the program never reaches a checker on either side.
    assert r.returncode in (0, 1, 2), "brat-cxx check rc=%d %s" % (r.returncode, r.stderr[-300:])
    assert not r.stderr, (path, r.stderr)
    return r.stdout, r.returncode


# Programs the loader refuses before any checker runs, and the words it uses.
# They are in the corpus on purpose: a refusal is part of the contract.
REFUSED = {"examples/own_priv.brat": "function `helper` is private in module `modapi`"}


FIXTURES = {
    'ret.brat': 'fn f(a: i64) -> i64 {\n  return "x"\n}\n',
    'arg.brat': 'fn f(a: i64) -> i64 {\n  return a\n}\nlet x = f("s")\n',
    'arity.brat': 'fn f(a: i64) -> i64 {\n  return a\n}\nlet x = f()\n',
    'ann.brat': 'let x: i64 = "s"\n',
    'meth.brat': 'let v = [1, 2]\nprint(v.nope())\n',
    'field.brat': 'let s = Point { x: 1 }\nprint(s.y)\n',
    'setfield.brat': 'let s = Point { x: 1 }\ns.y = 2\n',
    'push.brat': 'let mut v = [1]\nv.push("s")\n',
    'setidx.brat': 'let mut v = [1]\nv[0] = "s"\n',
    'setidx_ok.brat': 'let mut w = [1.5]\nw[0] = 2\nlet mut u = []\nu[0] = "s"\n',
    'assign.brat': 'let mut x: i64 = 1\nx = "s"\n',
    'slice.brat': 'print(slice_len(1, 2))\n',
    'sliceptr.brat': 'print(slice_of_ptr(1, 2, "f16"))\n',
    'libopen.brat': 'let p = lib_open(1)\n',
    'call.brat': 'print(call(1, "i64(i64)", "s"))\n',
    'forrange.brat': 'for i in 0.5..3 {\n  print(i)\n}\n',
    'own.brat': 'let x = own(1, 2)\n',
    'strmeth.brat': 'let s = str(1)\nprint(s.nope())\n',
    'mapget.brat': 'let m = {"a": 1}\nprint(m.get())\n',
    'arena.brat': 'fn f() -> i64 {\n  arena {\n    let v = [1]\n    return v\n  }\n}\n',
    'fnvalue.brat': 'fn double_it(x: i64) -> i64 {\n  return x * 2\n}\nlet g = double_it\n',
    'fnarg.brat': 'fn double_it(x: i64) -> i64 {\n  return x * 2\n}\nlet v = [1]\nprint(v.map(double_it))\n',
    'cb_ok.brat': 'fn cmp(a: i64, b: i64) -> i64 {\n  return a - b\n}\nfn run(f: fn(i64, i64) -> i64) -> i64 {\n  return f(1, 2)\n}\nlet x = run("cmp")\n',
    'cb_arity.brat': 'fn one(a: i64) -> i64 {\n  return a\n}\nfn run(f: fn(i64, i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("one")\n',
    'cb_default_arity.brat': 'fn one(a: i64, b: i64 = 0) -> i64 {\n  return a + b\n}\nfn run(f: fn(i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("one")\n',
    'cb_param_abi.brat': 'fn wrong(a: f64) -> i64 {\n  return 1\n}\nfn run(f: fn(i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("wrong")\n',
    'cb_ret_abi.brat': 'fn wrong(a: i64) -> f64 {\n  return 1.0\n}\nfn run(f: fn(i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("wrong")\n',
    'cb_width_abi.brat': 'fn wrong(a: i32) -> i64 {\n  return a\n}\nfn run(f: fn(i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("wrong")\n',
    'cb_unknown.brat': 'fn run(f: fn(i64) -> i64) -> i64 {\n  return 1\n}\nlet x = run("nope")\n',
    'multi.brat': 'fn f(a: i64) -> i64 {\n  return "x"\n}\nfn g(a: i64) -> i64 {\n  return a\n}\nlet x = g(f(1), g(2))\nlet y: str = 3\nlet v = [1]\nv.push("s")\nv.push(2, 3)\n',
    # A closure inside a placeholder, on the first line of its literal and on the second.
    'interp_line.brat': 'fn f(a: i64) -> i64 {\n  return a\n}\nlet v = [1]\nprint("{v.map(fn(x) { return f() })}")\nprint("two\n{v.map(fn(x) { return f() })}")\n',
    # A fn with a declared result returns on every path; `raise`, a `while true`
    # without `break` and a `match` over variants count as leaving.
    'no_return.brat': ('enum Light {\n  Red,\n  Green\n}\n'
                       'fn code(l: Light) -> i64 {\n  match l {\n    Red => { return 1 },\n'
                       '    Green => { return 2 }\n  }\n}\n'
                       'fn must(n: i64) -> i64 {\n  if n > 0 {\n    return n\n  }\n  raise("not positive")\n}\n'
                       'fn wait(n: i64) -> i64 {\n  while true {\n    if n > 0 {\n      return n\n    }\n  }\n}\n'
                       'fn sign(n: i64) -> i64 {\n  if n > 0 {\n    return 1\n  }\n}\n'
                       'fn name(n: i64) -> str {\n  match n {\n    0 => { return "zero" },\n'
                       '    1 => { return "one" }\n  }\n}\n'
                       'fn stop(n: i64) -> i64 {\n  while true {\n    if n > 0 {\n      break\n    }\n  }\n}\n'),
    # A builtin method calls its callback with one element, `fold` with two values.
    'cb_count.brat': ('fn less(a: i64, b: i64) -> bool {\n  return a < b\n}\n'
                      'let mut v = [3, 1, 2]\nv.sort_by(fn(a, b) { return a < b })\nv.sort_by(less)\n'
                      'print(v.fold(0, fn(a) { return a }))\n'
                      'v.sort_by(fn(x) { return 0 - x })\nprint(v.fold(0, fn(a, x) { return a + x }))\n'),
    # `get` hands back the value or `None`; only a method of the program's own can say `Some`.
    'match_get.brat': ('impl Cache {\n  fn get(self, k: str) -> Option[i64] {\n    return Some(self.n)\n  }\n}\n'
                       'let m = {"a": 1}\nmatch m.get("a") {\n  Some(x) => { print(x) },\n  None => { print(0) }\n}\n'
                       'match m.get("a") {\n  None => { print(0) },\n  x => { print(x) }\n}\n'
                       'let c = Cache { n: 7 }\nmatch c.get("a") {\n  Some(x) => { print(x) },\n  None => { print(0) }\n}\n'),
    # `+` does not turn a number into text and a bool is not a number; a "{...}"
    # placeholder takes any value. `if` and `while` test a bool.
    'no_coerce.brat': ('fn pick(x) {\n  let n = 5\n  let ok = n > 3\n  print("n=" + n)\n  print(1.5 + "s")\n'
                       '  print(ok + 1)\n  print(-ok)\n  print("n={n} ok={ok}" + str(n))\n'
                       '  if "x" {\n    print(1)\n  }\n  while n {\n    break\n  }\n'
                       '  if [n] {\n    print(2)\n  }\n  if x {\n    print(3)\n  }\n  return x + 1\n}\n'),
    # A fn that can `raise` hands its caller an `Err`: a call that drops the
    # result loses it. A `raise` under the fn's own `try` does not leave the fn.
    'raise_drop.brat': ('fn save(n) {\n  if n > 9 {\n    raise("too big")\n  }\n  return n\n}\n'
                        'fn guarded(n) {\n  try {\n    raise("inside")\n  } catch e {\n    return 0\n  }\n  return n\n}\n'
                        'fn run() {\n  save(1)\n  guarded(1)\n  let _ = save(2)\n  let kept = save(3)\n'
                        '  try {\n    save(4)\n    save(5)?\n  } catch e {\n    print(e)\n  }\n  return kept\n}\n'
                        # A `raise` in an `else` counts; one in a nested fn belongs to that fn.
                        # A parameter called `save` is not the fn `save`.
                        'fn outer(n) {\n  fn inner(k) {\n    raise("k")\n  }\n  return n\n}\n'
                        'fn other(n) {\n  if n > 0 {\n    return n\n  } else {\n    raise("neg")\n  }\n}\n'
                        'fn more() {\n  outer(1)\n  other(1)\n  return 0\n}\n'
                        'fn shadow(save) {\n  save(1)\n  return 0\n}\n'
                        # A `try` catches for its own statements, not for a closure written in it.
                        'fn deep() {\n  try {\n    let f = fn() {\n      save(6)\n      return 0\n    }\n    print(f())\n'
                        '  } catch e {\n    print(e)\n  }\n  return 0\n}\n'),
    # A call declared to return a `Result` cannot stand as a statement: a fn that
    # passes an `Err` on with `?`, one that relays another fn, a method, a
    # builtin, a std fn, an `Err(...)` written out.
    'result_drop.brat': ('import std.fs\nstruct Box { cap: i64 }\n'
                         'impl Box {\n  fn make(cap: i64) -> Result[Box, str] {\n    if cap < 0 {\n      return Err("negative")\n    }\n'
                         '    return Ok(Box { cap: cap })\n  }\n'
                         '  fn put(self, n: i64) -> Result[i64, str] {\n    if n > self.cap {\n      return Err("too big")\n    }\n'
                         '    return Ok(n)\n  }\n}\n'
                         'fn port(text: str) -> Result[i64, str] {\n  let n = text.parse_int()?\n  return Ok(n)\n}\n'
                         'fn relay(text: str) -> Result[i64, str] {\n  return port(text)\n}\n'
                         'fn both(n: i64) -> Result[i64, str] {\n  if n > 9 {\n    raise("too big")\n  }\n  return Ok(n)\n}\n'
                         'fn dropped(b: Box) -> i64 {\n  port("x")\n  relay("x")\n  b.put(12)\n  Box.make(-1)\n'
                         '  write_file("x.txt", "y")\n  fs.remove("x.txt")\n  "12".parse_int()\n  Err("lost")\n  both(12)\n'
                         # A `try` does not take the `Result` of a statement in it: `?` does. A fn
                         # that raises keeps the rule of `raise_drop.brat`.
                         '  try {\n    port("x")\n    both(12)\n  } catch e {\n    print(e)\n  }\n'
                         # A statement in a closure body drops its value like any other.
                         '  let f = fn() {\n    port("x")\n    return 0\n  }\n  return f()\n}\n'
                         # Taken in the open: `let _ =`, `?`, `match`, `?` under a `try`.
                         'fn kept(b: Box) -> Result[i64, str] {\n  let _ = port("x")\n  let _ = b.put(12)\n'
                         '  let _ = fs.remove("x.txt")\n  port("x")?\n  b.put(1)?\n'
                         '  match relay("x") {\n    Ok(n) => print(n),\n    Err(why) => print(why),\n  }\n'
                         '  try {\n    port("x")?\n    write_file("x.txt", "y")?\n  } catch e {\n    print(e)\n  }\n'
                         '  let n = relay("1")?\n  return Ok(n)\n}\n'),
    # The arguments after a closure belong to the statement, not to the closure's last line.
    # The body of `scope { }` is checked like any other block. The type pass
    # skipped it: a call with the wrong arguments went to the C compiler, and an
    # `Err` dropped there was dropped in silence.
    'scope_types.brat': ('fn add(a: i64, b: i64) -> i64 { return a + b }\n'
                         'fn boom(n: i64) -> i64 {\n  if n > 0 { raise("task failed") }\n  return 0\n}\n'
                         'fn main() -> i64 {\n  scope {\n    print(add(1, "x"))\n    let n: i64 = "text"\n'
                         '    boom(1)\n    spawn { boom(2) }\n    spawn {\n      print(add(2))\n    }\n'
                         '    spawn { boom(3)? }\n  }\n  return 0\n}\n'),
    'closure_line.brat': 'fn f(a: i64) -> i64 {\n  return a\n}\nfn apply(g, x) {\n  return g(x)\n}\nprint(apply(fn(x) {\n  return x\n}, f(1, nope)))\n',
    # A variable or an element that holds a `Result` loses its `Err` as a statement too.
    'result_bare.brat': ('fn port(text: str) -> Result[i64, str] {\n  let n = text.parse_int()?\n  return Ok(n)\n}\n'
                         'fn bare() -> i64 {\n  let r = port("x")\n  r\n  let v = [port("1"), port("2")]\n  v[0]\n'
                         '  let _ = r\n  let _ = v[1]\n  return 0\n}\n'),
    # A fn declared in a body and a closure bound by `let` drop an `Err` as a statement too.
    'local_drop.brat': ('fn port(n: i64) -> Result[i64, str] {\n  return Ok(n)\n}\n'
                        'fn bare() -> i64 {\n  fn inner(n: i64) -> Result[i64, str] {\n    return port(n)\n  }\n'
                        '  inner(2)\n  fn boom(n) {\n    raise("x")\n  }\n  boom(1)\n'
                        '  let f = fn(n) {\n    raise("x")\n  }\n  f(1)\n'
                        '  let _ = inner(3)\n  let _ = boom(1)\n  let _ = f(2)\n'
                        '  let mut g = fn(n) {\n    raise("x")\n  }\n  g = fn(n) {\n    return n\n  }\n  g(1)\n'
                        '  return 0\n}\n'),
}


def result_dropped(line):
    return ("result_drop.brat:%d: error: the `Result` of this call is dropped here "
            "(hint: `match` handles it, `?` after the call passes an `Err` on, `let _ = ...` ignores it)" % line)


# Expected errors, including source locations.
EXPECT = {
    "ret.brat": ["ret.brat:2: error: return: want i64, got str"],
    "arg.brat": ["arg.brat:4: error: arg 1 of `f`: want i64, got str"],
    "arity.brat": ["arity.brat:4: error: `f` wants 1 args, got 0"],
    "ann.brat": ["ann.brat:1: error: let `x`: annotated i64, got str"],
    "meth.brat": ["meth.brat:2: error: no method `nope` for vec[i64]"],
    "field.brat": ["field.brat:2: error: no field `y` on struct (has x)"],
    "result_bare.brat": [
        "result_bare.brat:7: error: this `Result` is dropped here "
        "(hint: `match` handles it, `?` after it passes an `Err` on, `let _ = ...` ignores it)",
        "result_bare.brat:9: error: this `Result` is dropped here "
        "(hint: `match` handles it, `?` after it passes an `Err` on, `let _ = ...` ignores it)",
    ],
    "local_drop.brat": [
        "local_drop.brat:8: error: the `Result` of this call is dropped here "
        "(hint: `match` handles it, `?` after the call passes an `Err` on, `let _ = ...` ignores it)",
        "local_drop.brat:12: error: `boom` can raise, and the `Err` it returns is dropped here "
        "(hint: `boom(...)?` passes it on, `let _ = boom(...)` ignores it)",
        "local_drop.brat:16: error: `f` can raise, and the `Err` it returns is dropped here "
        "(hint: `f(...)?` passes it on, `let _ = f(...)` ignores it)",
    ],
    "setfield.brat": [
        "setfield.brat:2: error: assign to immutable `s.y` (want `let mut` or mut param)",
        "setfield.brat:2: error: no field `y` on struct (has x)",
    ],
    "push.brat": ["push.brat:2: error: method `push` arg 1: want i64, got str"],
    "setidx.brat": ["setidx.brat:2: error: assign to an element of `v`: want i64, got str"],
    "setidx_ok.brat": [],
    "assign.brat": ["assign.brat:2: error: assign to `x`: want i64, got str"],
    "slice.brat": ["slice.brat:1: error: `slice_len` wants 1 args, got 2"],
    "sliceptr.brat": ["sliceptr.brat:1: error: slice_of_ptr: kind must be the literal \"i64\", \"i32\", \"f64\", \"f32\" or \"u8\""],
    "libopen.brat": ["libopen.brat:1: error: lib_open: want str, got i64"],
    "call.brat": ["call.brat:1: error: call: arg 1 wants i64, got str"],
    "forrange.brat": ["forrange.brat:1: error: forrange bound: want i64, got f64"],
    "own.brat": ["own.brat:1: error: `own` wants 1 arg, got 2"],
    "strmeth.brat": ["strmeth.brat:2: error: no method `nope` for str"],
    "mapget.brat": ["mapget.brat:2: error: method `get` wants 1 args"],
    "arena.brat": [
        "arena.brat:4: error: arena: a value made inside the block is returned out of it  (hint: hand out a heap copy with `own(...)`, e.g. `return Err(own(msg))`)",
        "arena.brat:4: error: return: want i64, got vec[i64]",
    ],
    "fnvalue.brat": ["fnvalue.brat:4: error: use of `double_it` as a value: a fn name is a callback, not a value (hint: call it: `double_it()`)"],
    "fnarg.brat": [],
    "cb_ok.brat": [],
    "cb_arity.brat": ["cb_arity.brat:7: error: callback `one` takes 1 parameter(s), fn(i64,i64)->i64 wants 2"],
    "cb_default_arity.brat": ["cb_default_arity.brat:7: error: callback `one` takes 2 parameter(s), fn(i64)->i64 wants 1"],
    "cb_param_abi.brat": ["cb_param_abi.brat:7: error: callback `wrong` has signature fn(f64)->i64, expected fn(i64)->i64"],
    "cb_ret_abi.brat": ["cb_ret_abi.brat:7: error: callback `wrong` has signature fn(i64)->f64, expected fn(i64)->i64"],
    "cb_width_abi.brat": ["cb_width_abi.brat:7: error: callback `wrong` has signature fn(i32)->i64, expected fn(i64)->i64"],
    "cb_unknown.brat": ["cb_unknown.brat:4: error: unknown callback `nope`"],
    "multi.brat": [
        "multi.brat:10: error: cannot mutate immutable `v`: `v.push` writes through it",
        "multi.brat:11: error: cannot mutate immutable `v`: `v.push` writes through it",
        "multi.brat:2: error: return: want i64, got str",
        "multi.brat:7: error: `g` wants 1 args, got 2",
        "multi.brat:8: error: let `y`: annotated str, got i64",
        "multi.brat:10: error: method `push` arg 1: want i64, got str",
        "multi.brat:11: error: method `push` wants 1 args",
    ],
    "interp_line.brat": [
        "interp_line.brat:5: error: `f` wants 1 args, got 0",
        "interp_line.brat:7: error: `f` wants 1 args, got 0",
    ],
    "no_return.brat": [
        "no_return.brat:25: error: `sign` is declared `-> i64` but can end without a `return`",
        "no_return.brat:30: error: `name` is declared `-> str` but can end without a `return`",
        "no_return.brat:36: error: `stop` is declared `-> i64` but can end without a `return`",
    ],
    "cb_count.brat": [
        "cb_count.brat:5: error: method `sort_by` wants a callback with 1 args, got 2 (it orders by the key the callback returns)",
        "cb_count.brat:6: error: method `sort_by` wants a callback with 1 args, got 2 (it orders by the key the callback returns)",
        "cb_count.brat:7: error: method `fold` wants a callback with 2 args, got 1",
    ],
    "match_get.brat": [
        "match_get.brat:7: error: non-exhaustive match: `get` answers the value itself or `None`, so `Some(...)` never matches (hint: match `None` and `_`)",
    ],
    "no_coerce.brat": [
        "no_coerce.brat:4: error: operator `+` joins two strings, got str and i64 (hint: `str(x)` makes the string)",
        "no_coerce.brat:5: error: operator `+` joins two strings, got str and f64 (hint: `str(x)` makes the string)",
        "no_coerce.brat:6: error: operator `+` wants numbers, got bool",
        "no_coerce.brat:7: error: unary `-` wants a number, got bool",
        "no_coerce.brat:9: error: condition wants bool, got str",
        "no_coerce.brat:12: error: condition wants bool, got i64",
        "no_coerce.brat:15: error: condition wants bool, got vec[i64]",
    ],
    "raise_drop.brat": [
        "raise_drop.brat:16: error: `save` can raise, and the `Err` it returns is dropped here "
        "(hint: `save(...)?` passes it on, `let _ = save(...)` ignores it)",
        "raise_drop.brat:43: error: `other` can raise, and the `Err` it returns is dropped here "
        "(hint: `other(...)?` passes it on, `let _ = other(...)` ignores it)",
        "raise_drop.brat:53: error: `save` can raise, and the `Err` it returns is dropped here "
        "(hint: `save(...)?` passes it on, `let _ = save(...)` ignores it)",
    ],
    "result_drop.brat": (
        [result_dropped(line) for line in range(31, 39)]
        + ["result_drop.brat:39: error: `both` can raise, and the `Err` it returns is dropped here "
           "(hint: `both(...)?` passes it on, `let _ = both(...)` ignores it)"]
        + [result_dropped(41), result_dropped(47)]
    ),
    "scope_types.brat": [
        "scope_types.brat:8: error: arg 2 of `add`: want i64, got str",
        "scope_types.brat:9: error: let `n`: annotated i64, got str",
        "scope_types.brat:10: error: `boom` can raise, and the `Err` it returns is dropped here "
        "(hint: `boom(...)?` passes it on, `let _ = boom(...)` ignores it)",
        "scope_types.brat:11: error: `boom` can raise, and the `Err` it returns is dropped here "
        "(hint: `boom(...)?` passes it on, `let _ = boom(...)` ignores it)",
        "scope_types.brat:13: error: `add` wants 2 args, got 1",
    ],
    "closure_line.brat": [
        "closure_line.brat:7: error: use of undeclared var `nope`",
        "closure_line.brat:7: error: `f` wants 1 args, got 2",
    ],
}


# Expected ownership failures in shipped examples. Other loaded corpus sources
# must check without errors or warnings.
CORPUS_ERRORS = {
    "examples/own_bad.brat": [
        "4: error: ref `r` escapes via return",
        "8: error: double mut borrow of `m`: `a2` clashes with `a1`",
        "9: error: use of undeclared var `nope`",
        "10: error: ref `a1` escapes via spawn",
    ],
    "examples/own_move.brat": [
        "7: error: use of moved `h` (hint: the value was moved; use a copy or re-bind)",
        "14: error: use of moved `p` (hint: the value was moved; use a copy or re-bind)",
    ],
    "examples/own_paths_bad.brat": [
        "3: error: use of moved `p.x`",
        "4: error: use of moved `p`",
        "5: error: use of moved `p` (hint: the value was moved; use a copy or re-bind)",
    ],
    "examples/own_sig.brat": [
        "12: error: use of moved `h` (hint: the value was moved; use a copy or re-bind)",
    ],
}

# Expected unused bindings in fixtures and deliberately rejected examples.
UNUSED = {
    "examples/own_bad.brat": [(8, "a2")],
    "examples/own_move.brat": [(6, "m"), (9, "r"), (13, "q")],
    "examples/own_paths_bad.brat": [(2, "a"), (4, "q")],
    "examples/own_sig.brat": [(11, "r"), (14, "q"), (16, "z")],
    "arg.brat": [(4, "x")],
    "arity.brat": [(4, "x")],
    "ann.brat": [(1, "x")],
    "libopen.brat": [(1, "p")],
    "own.brat": [(1, "x")],
    "fnvalue.brat": [(4, "g")],
    "cb_ok.brat": [(7, "x")],
    "cb_arity.brat": [(7, "x")],
    "cb_default_arity.brat": [(7, "x")],
    "cb_param_abi.brat": [(7, "x")],
    "cb_ret_abi.brat": [(7, "x")],
    "cb_width_abi.brat": [(7, "x")],
    "cb_unknown.brat": [(4, "x")],
    "multi.brat": [(7, "x"), (8, "y")],
}

NOTES = {
    "examples/own_bad.brat": [
        "7: note: first borrow `a1` here",
        "note: help: in scope here are `let` bindings, fn parameters, `for` bindings and `match` arm bindings; functions come from `fn`/`impl`; a name from another file needs `import that.file`",
    ],
    "examples/own_move.brat": [
        "6: note: `h` moved here", "13: note: `p` moved here",
    ],
    "examples/own_paths_bad.brat": [
        "4: note: `p` moved here",
    ],
    "examples/own_sig.brat": ["11: note: `h` moved here"],
    "setfield.brat": ["1: note: `s` declared here without `mut` (help: `let mut s`)"],
    "fnvalue.brat": [
        "note: help: a bare fn name is a callback argument to `map`, `filter`, `fold`, `any`, `all`, `find` and `sort_by` only",
    ],
    "multi.brat": ["9: note: `v` declared here without `mut` (help: `let mut v`)"] * 2,
    "closure_line.brat": [
        "note: help: in scope here are `let` bindings, fn parameters, `for` bindings and `match` arm bindings; functions come from `fn`/`impl`; a name from another file needs `import that.file`",
    ],
}


def diagnostics(text, severity):
    return [line for line in text.splitlines() if ": %s: " % severity in line]


def check_rendering(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^(.*):(\d+): (error|warning|note): ", line)
        if match:
            path, number, _severity = match.groups()
            with open(path, encoding="utf-8") as stream:
                source = stream.read().splitlines()
            number = int(number)
            assert 1 <= number <= len(source), line
            assert i + 1 < len(lines) and lines[i + 1] == "  | " + source[number - 1], line
    ownership = re.findall(r"^(.*): (\d+) error\(s\), (\d+) warning\(s\)$", text, re.M)
    types = re.findall(r"^(.*): (\d+) type error\(s\)$", text, re.M)
    assert ownership and types, "missing checker summaries"
    assert {path for path, _errors, _warnings in ownership} == {path for path, _errors in types}
    errors = sum(int(count) for _path, count, _warnings in ownership)
    errors += sum(int(count) for _path, count in types)
    warnings = sum(int(count) for _path, _errors, count in ownership)
    assert errors == len(diagnostics(text, "error")), text
    assert warnings == len(diagnostics(text, "warning")), text


def main():
    _cxx.build()
    start = time.perf_counter()
    assert FIXTURES.keys() == EXPECT.keys(), "each fixture needs explicit errors (possibly empty)"
    fixtures = {}
    for name, source in FIXTURES.items():
        path = os.path.join(TMP, name)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(source)
        fixtures[name] = path

    corpus = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("vendor", "bin", ".git", "__pycache__")]
        corpus.extend(os.path.join(base, name) for name in files if name.endswith(".brat"))
    corpus.sort()
    assert corpus, "no source corpus"
    corpus_names = {os.path.relpath(path, ROOT).replace(os.sep, "/") for path in corpus}
    assert set(CORPUS_ERRORS) | set(REFUSED) <= corpus_names
    assert set(UNUSED) | set(NOTES) <= corpus_names | set(FIXTURES)
    refused = 0
    for path in corpus + [fixtures[name] for name in sorted(fixtures)]:
        is_fixture = path in fixtures.values()
        name = os.path.basename(path) if is_fixture else os.path.relpath(path, ROOT).replace(os.sep, "/")
        got, rc = cxx(path)
        if not is_fixture and name in REFUSED:
            assert rc == 2 and REFUSED[name] in got, (path, rc, got)
            refused += 1
            continue

        errors = EXPECT[name] if is_fixture else [name + ":" + line for line in CORPUS_ERRORS.get(name, [])]
        warnings = ["%s:%d: warning: unused var `%s`" % (name, line, binding)
                    for line, binding in UNUSED.get(name, [])]
        notes = [name + ":" + (" " if line.startswith("note:") else "") + line
                 for line in NOTES.get(name, [])]
        prefix = path if is_fixture else ROOT + os.sep
        replacement = name if is_fixture else ""
        normalized = got.replace(prefix, replacement)
        if os.sep != "/" and not is_fixture:
            for rel in corpus_names:
                normalized = normalized.replace(rel.replace("/", os.sep) + ":", rel + ":")
        for severity, expected in (("error", errors), ("warning", warnings), ("note", notes)):
            actual = diagnostics(normalized, severity)
            assert actual == expected, "%s %s: want %r, got %r" % (name, severity, expected, actual)
        assert rc == (1 if errors else 0), (path, rc, errors)
        check_rendering(got)

    assert refused == len(REFUSED), (refused, REFUSED)
    missing, rc = cxx(os.path.join(TMP, "nope.brat"))
    assert rc == 2 and "load error" in missing, (rc, missing)
    print("CXX CHECKER ALL GREEN (%d corpus + %d fixtures, explicit diagnostics, %.2fs)"
          % (len(corpus), len(fixtures), time.perf_counter() - start))


if __name__ == "__main__":
    main()
