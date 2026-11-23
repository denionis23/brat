# BRAT 0.7

BRAT is a small language that compiles to C11. This file describes what the
compiler in `lang/cxx/src/` and the runtime in `lang/engine/` do today. Where
the two disagree with this file, they win and this file has a bug.

A short orientation first. A program is a set of `.brat` files. `brat check`
parses them, resolves imports, checks types and ownership, and stops. `brat run`
and `brat build` go on to emit C and hand it to the system C compiler. Types are
optional: an annotated function compiles to plain C over `int64_t` and `double`,
an unannotated one works on 16-byte tagged values. Memory is reference counted.
Ownership is checked inside one function at a time and not across calls.

Contents: 1 Source, 2 Values and types, 3 Expressions, 4 Statements, 5 Functions,
6 Structs, enums, traits, 7 Errors, 8 Ownership, 9 Arenas, 10 Threads,
11 Modules and packages, 12 C interop, 13 Built-ins, 14 Standard library,
15 Command line, 16 Diagnostics, 17 Limits, 18 Implementation, 19 Known gaps.

## 1. Source

Files are UTF-8 and contain no NUL byte. A comment starts with `//` and runs to
the end of the line.

Identifiers are `[A-Za-z_][A-Za-z0-9_]*`. These words are keywords:

`fn`, `pub`, `let`, `mut`, `move`, `return`, `if`, `else`, `while`, `for`, `in`,
`break`, `continue`, `match`, `enum`, `trait`, `impl`, `import`, `use`, `const`,
`self`, `or`, `try`, `catch`, `defer`, `spawn`, `extern`, `export`, `unsafe`,
`true`, `false`.

`struct`, `scope`, `par`, `reduce` and `arena` only mean something where the
parser expects them and are ordinary names elsewhere. A keyword cannot name a
binding, a function or a parameter (`self` is the exception).

Integer literals are decimal, `0x`, `0o` or `0b`, with `_` allowed between
digits. A decimal literal has to fit `i64`; write `-9223372036854775808` with its
minus. A hex, octal or binary literal may use all 64 bits and is read as two's
complement, so `0xFFFFFFFFFFFFFFFF` is `-1`. Anything wider is an error. A
literal with `.` or an exponent is an `f64`.

A string literal is in double quotes and interpolates `{expr}`. A brace pair
that does not hold an expression stays text, so `"{\"a\": 1}"` is JSON. The
escapes are `\n \t \r \\ \" \' \{ \}`, `\x1b` (two hex digits, up to `7f`) and
`é` or `\u{1F600}`. Any other backslash stays as written, which lets
`"\d+"` be a regex without doubling. A literal that contains NUL is an error.

Separators in call arguments and in vector, map and struct literals are commas,
and a trailing comma is allowed.

## 2. Values and types

The scalar types are `i64`, `f64`, `bool` and `str`. The containers are
`vec[T]` and `map[K, V]`; a map keeps insertion order. `Option[T]` is
`Some(T) | None` and `Result[T, E]` is `Ok(T) | Err(E)`. A function type is
`fn(T1, ...) -> R`. There are also `chan`, socket, SQLite and plugin handles, and
the C-boundary types in section 12.

Integers are 64-bit and signed, and nothing else exists outside the C boundary.
`str` is valid UTF-8, and `len`, indexing and iteration count code points, not
bytes or grapheme clusters.

Types are optional. A binding or parameter without an annotation has type `Dyn`,
which the checker accepts wherever a type is declared. Annotations are checked
at compile time only. Nothing checks them at run time, so
`fn add(a: i64, b: i64) -> i64`, called through an unannotated function with a
string, will run `+` on that string.

`let x = e` is immutable. `let mut x = e` can be reassigned and mutated. `const`
is a top-level immutable. A struct literal `Point { x: 3, y: 4 }` needs no
declaration; declaring `struct Point { x: i64, y: i64 }` fixes the fields and
gives a flat layout.

A fn, a struct, an enum, a variant and a trait each have one name in a file. Two
of the same name, or a fn named like a struct, an enum, a variant or a built-in
such as `len`, is an error, because a call by that name would reach the
built-in. A `pub fn` is exempt: the file that imports it gets it in place of the
built-in.

Nothing converts implicitly. `"a" + 5`, `true + 1` and `if n` on an `i64` are
compile errors where the types are known. Where they are not, `+` still joins a
string and a number at run time (`1 + "a"` gives `1a`). Use `str(n)`, a
`"{n}"` placeholder, and `n != 0`.

## 3. Expressions

Operators, from tight to loose: unary `-` `!` `~` `&`; `*` `/` `%`; `+` `-`;
`<<` `>>`; `&`; `^`; `|`; comparisons and `in`; `&&`; `||`; `or`. There is no
`**`. Postfix: call, index, field, method call, `?`.

Integer arithmetic.
- `+`, `-`, `*` and unary `-` wrap in two's complement.
- `/` on integers rounds toward negative infinity and `%` takes the sign of the
  divisor: `-7 / 2` is `-4`, `-7 % 2` is `1`, `7 % -2` is `-1`.
- `/` and `%` by zero raise `div by zero`, on `i64` and on `f64`.
  `INT64_MIN / -1` wraps to `INT64_MIN`, and `INT64_MIN % -1` is `0`.
- A shift uses the low six bits of the count, so `1 << 64` is `1`. `>>`
  sign-extends.

Floats follow IEEE 754: overflow gives `inf`, `NaN == NaN` is false. An integer
next to a float becomes a float. `i64(x)` drops the fraction toward zero and
raises `integer out of range` when the value does not fit, `f64(x)` converts the
other way, and both raise `not a number` for anything else.

`==` and `!=` compare structurally and never coerce: `1 == "1"` is false.
`if` and `while` need a `bool`; a condition known to be a string, number, vector
or map is a compile error.

`+` adds numbers or joins strings. `s * n` repeats a string. `x in v`,
`t in s` and `k in m` test membership. `"{expr}"` formats any value.

Indices are `i64`, or an `f64` that is a whole number (`v[2.0]`). A fractional
float, a `bool`, `nan` and `inf` raise `index must be int`. `v[i]` outside
`0..len(v)` raises `index out of range`, and `m[k]` on a missing key raises
`no key`. Variants such as `Ok(42)` cannot be indexed.

Map keys keep their tag: `1`, `1.0` and `true` are three keys. A vector, a map,
a struct or a closure cannot be a key; storing under one raises
`unhashable map key` and `m.has(k)` is false.

`chr(n)` makes the one-character string of code point `n` and raises
`not a code point` for a surrogate or a value outside `0..0x10FFFF`. `ord(s)`
is the inverse and raises `ord wants one character` otherwise.

## 4. Statements

`if` / `else`, `while`, `for`, `match`, `try` / `catch`, `defer`, `return`,
`break`, `continue`, `arena`, `scope`, `spawn` and `unsafe` are statements.
`for i in a..b` stops before `b`; `for x in coll` walks a vector, a map's keys,
or a string's code points. `if let Pat = e { }` and `while let Pat = e { }`
match one pattern.

`match` has to cover every case of an enum, an `Option`, a `Result` or a `bool`,
or end in `_`; a missing case is a compile error. A `match` has a value only in
`return match x { ... }`.

`defer expr` runs when its block ends, last in first out, however the block
ends: normally, `return`, `break`, `continue`, `?` or `raise`.

`unsafe { }` marks raw pointer and C sections. It turns nothing off: types,
exclusivity and move tracking still apply inside it.

A top-level statement is not a function body. A `fn` declared inside a top-level
`if` or loop is an error.

## 5. Functions and closures

```brat
fn area(w: i64, h: i64) -> i64 { return w * h }
fn describe(x) { return "something" }
let twice = fn(n) { return n * 2 }
```

A function returns with `return`; the last expression is not returned for you. A
function that declares `-> T` and can reach its end is a compile error. An `if`
with an `else`, a `match` over variants and a `while true` without `break` count
as leaving when each branch leaves.

A default parameter value is written `b: i64 = 10`. Generic parameters are
written `fn first<T>(v) -> i64`; they are erased, see section 17.

An annotated function (`i64`, `f64`, `bool`, `vec[i64]`, `vec[f64]` and
combinations) is compiled twice: an unboxed C function for typed callers and a
thin wrapper for dynamic callers and closures.

A closure gets a shallow copy of every binding it uses. It can read the copy but
not assign to it, not `move` an outer non-`Copy` capture, and not take over an
outer `move ptr`. A vector or map behind the binding is shared, which is where a
counter keeps its state. A top-level `let` is not captured: every function and
closure reads and writes the one value.

A named function is a callback, not a value. It can be passed by name to `map`,
`filter`, `fold`, `any`, `all`, `find` and `sort_by` (an imported `pub fn` as
`area` or `shape.area`), or as a string to a C callback parameter, but
`let f = double` is an error. Wrap it in a closure. A local or parameter named
like a function shadows it, also in calls.

A `fn` inside another function is a name of that function only and does not
capture: its body sees its own parameters and the top-level names. A block takes
one `fn` per name; sibling blocks may each declare their own.

## 6. Structs, enums, traits

```brat
struct Rect { w: i64, h: i64 }
enum Shape { Box(r), Circle(radius: i64), Dot }
trait Shout { fn loud(self) -> i64 }

impl Rect {
  fn square(side: i64) { return Rect { w: side, h: side } }
  fn area(self) -> i64 { return self.w * self.h }
}
impl Shout for Rect { fn loud(self) -> i64 { return self.w * 2 } }
```

`impl` adds methods (they take `self`) and functions called on the type
(`Rect.square(4)`). An `impl Trait for T` that leaves a method out is an error.
There are no trait objects. Variant names belong to the whole program: `Busy` is
one tag everywhere, and two enums may share it only with the same number of
fields. A local struct that does not escape is split into C locals at `-O2`.

## 7. Errors

There are two channels and they meet at `?`.

A function that can fail returns `Ok(v)` or `Err(e)`. `expr?` unwraps an `Ok` or
`Some`. In a function that returns `Result` or `Option` it returns the `Err` or
`None` at once. In any other function it raises the payload to the nearest `try`.

`raise(x)` leaves the function with `Err(x)`, or goes to a `try` around it in the
same function. A caller that takes the value sees an `Err` and decides with `?`
or `match`. A caller that writes the call as a statement gets the error in its
`catch`, as if it had written `?`. With no `try` around, that statement would lose
the error and is a compile error. `try { } catch e { }` binds the payload itself.

Run-time faults (index out of range, missing key, division by zero,
`recursion too deep`, a failed `assert`) unwind to the nearest `try` in the same
way.

A call whose declared type is `Result` (a function or method with
`-> Result[...]`, a built-in such as `write_file`, a module function such as
`fs.remove`) cannot stand as a statement, in a `try` as well. Match it, pass it
on with `?`, or drop it openly with `let _ = ...`. The same goes for a variable
or element of type `Result`, and for a fn declared in a body, or a closure bound
by `let` (not `let mut`), whose body calls `raise`. `defer` is not covered, since
it has no `let _`. The checker reads the body of a function it can name; a call
through a method, a parameter or a closure held in a variable is treated as `?`.

Lookups that can be empty answer the value or `None`, not `Some(...)`: `m.get`,
`v.first`, `v.find`, `s.index_of`. Test with `is_none(x)` or supply a fallback
with `x or fallback`.

An error that reaches the top prints `unhandled: Err('...')` on stderr and the
program exits with status 1. `brat run` below `-O2` adds ` at file.brat:N`;
`-O2` and `build` add it only with `--trace-lines` (it costs a store per
statement), and `BRAT_TRACE=0` removes it.

## 8. Ownership

The checker (`borrow.cpp`) follows who owns each value inside one function. It
has no lifetime annotations and does not follow borrows across calls: between
functions a value is kept alive by its reference count. It catches the local
mistakes and is not a proof. It tracks paths `x`, `x.f`, `x.f.g` and `x[i]`, with
every index of `x` counted as one place.

Parameters say how they take an argument:
- `x: T` (`ref`, the default) reads it for the length of the call.
- `mut x: T` reads and writes it. The argument must be a `let mut` that nothing
  else in the same call uses.
- `move x: T` takes it over. The caller's name is dead afterwards unless `T` is a
  number or bool, which are copied.

`move x` kills the whole name. `move p.x` kills only that field: `p.y` stays
readable and a second read of `p.x` is `E0382`. At run time the slot is not
emptied; the field's count goes up and the slot keeps its reference until `p.x`
is overwritten or `p` is dropped.

A borrow ends at the last read of the name that holds it. Branches are merged
without looking at their conditions: after `if c { move s }` the value counts as
possibly moved, and a second `if !c { move s }` is refused. Write `else` or a
`match`. A branch that leaves the function keeps its moves to itself, so a guard
clause works. `break` and `continue` do not leave the function: a move before
`break` counts after the loop. A move in `try` counts in `catch`, because the
error may come after it; put cleanup in a `defer` before the `try` instead.

What is refused:

| Situation | Message |
|---|---|
| read after `move` | `use of moved x`, with a note where it moved |
| `move` while a borrow is live | `cannot move x while borrowed by y` |
| reassign without `let mut` | `assign to immutable x` |
| reassign a `const` | `assign to const x` |
| mutating method on an immutable binding | `cannot mutate immutable x` |
| immutable binding passed to a `mut` parameter | `pass immutable x as mut param p` |
| `mut` and `mut`, or `ref` and `mut`/`move`, on one root in one call; read on one side of an operator and `move` on the other | `law of exclusivity` (E0499) |
| move out of a borrowed parameter | `cannot move borrowed parameter` |
| a local borrow returned | `ref x escapes via return` |
| a local borrow captured by `spawn` | `ref x escapes via spawn` |
| container changed while a `for` walks it | `cannot mutate v while iterating it` |
| a `move ptr` not freed on every path | `leaked owned pointer p` |
| `impl` missing a trait method | `impl T for U missing m` |
| use after `ch.send(x)` | `use of sent x` |

A borrow lasts for its call: `f(x) + f(x)` is fine, and `fib(n-1, memo) +
fib(n-2, memo)` with a `mut memo` is fine. In `f(memo, g(memo))` the inner call
runs while `f` holds `memo`, and that is refused.

`for x in v` holds `v` for the whole body, directly or through a closure.
`for i in 0..len(v)` and `for x in v.copy()` do not. The loop variable owns its
element, so replacing or removing it through another name does not leave it
dangling.

A function that returns one of its by-reference parameters unchanged (`return p`)
hands back the same object, and the checker knows it: after
`let mut b = ident(a)`, `b` is another name for `a`. So `a` must be `let mut`
before `b` is allowed to mutate it, and the race check treats the two as one
value. Aliasing through any other shape of return (a field, a container, a
struct holding the parameter) is not followed.

A closure cannot assign to a capture, move it, or take a `move ptr`.

There is no cycle collector. The checker follows writes into containers inside
one function and refuses one that closes a cycle (`v.push(v)`). A cycle built
across functions is not seen and leaks. Keep long-lived graphs as indices into a
vector and build short-lived ones in an `arena`.

## 9. Arenas

`arena { ... }` allocates everything inside its dynamic extent, called functions
included, from a thread-local bump region and releases it in one step on exit,
however the block ends. Chunks are 64 KiB (a larger request opens one at least
twice the previous size); up to 4 chunks, 256 KiB, are kept per thread for the
next entry. Under AddressSanitizer the released bytes are poisoned.

`own(x)` deep-copies a value onto the ordinary heap. Scalars, strings of 14 bytes
or less and values already on the heap come back unchanged; the copy recurses at
most 2000 levels.

The checker rejects an arena value that is returned, assigned or pushed into a
binding declared outside the block (`outer = x`, `outer.push(x)`, `outer[k] = x`,
`outer.f = x`), sent on a channel, or used with `spawn`, a nested `par for`,
`ptr_write_*` or `slice_set`, unless it passes through `own(...)`.

A function called from the block can store its own results outside it, where the
checker does not see. For that the runtime copies at the store: a value that
lives in an arena and is written into a container, struct, map or global that does
not, is copied to the heap first. So `g.push(fresh())` in a called function is
safe, but costs a copy, and aliasing between the original and what the container
holds is gone. Channels and `raise` copy as well.

## 10. Threads

`spawn { }` runs a block on a worker thread. `scope { }` waits for every task
started inside it and re-raises the first uncaught worker error. `spawn` copies
the names it uses and shares the values behind them. `join_all()` and `join(h)`
wait too.

Between a `spawn` and the join, a binding written by a task cannot be read or
written by the parent or a sibling (`B0522`). Writes through C count: `writes(p)`,
`&x`, `ptr_write_*`, `slice_set`. The check follows the body of the task, calls
into functions with a known summary, and closures bound by `let` that are
passed on to such a function (`spawn { run(w) }` counts what `w` writes). It does
not follow a closure stored in a field or handed in as a parameter.

`chan(cap)` makes a bounded many-to-many queue, `1 <= cap <= 1,048,576`. A
capacity that is not an integer or is below 1 raises; one above the limit, or
past the total channel budget, returns an `Err`. `send` waits while full, moves or copies the value,
and raises on a closed channel. `recv` answers `None` once the channel is
closed and empty. `close` stops further sends.

When a task fails, the other tasks of its `scope` that wait on a channel, now or
later, end that wait with a cancellation error, and the scope raises the failure
that came first. A task is cancelled only at a channel wait. A failure inside a
nested `scope` belongs to that scope. A `send` or `recv` of `main` that would
wait for ever once every task has ended re-raises the failed task's error.

The end of a `scope` runs only tasks of that `scope`. `BRAT_THREADS` sets the
worker count (default the hardware count, at most 32). While every worker waits
on a channel or the end of a `scope` and work is queued, the pool adds a thread,
up to 4096; past that it prints one line to stderr. The run queue is unbounded.
There is no green-thread scheduler and no event loop.

`par for x in xs reduce(op, unit) { body }` runs the body on the pool and folds
the results with `op(acc, result)` in index order `0..len(xs)` on the calling
thread, so the result does not depend on scheduling. An empty input gives `unit`.
Checks: `op` names a declared function of two parameters; `op` and the body have
an empty effect row; neither writes outer state. Effects are inferred across the
call graph: `raise` (`?`, `raise`, `unwrap`, `assert`, `exit`), `io` (console,
files, network, SQLite, channels, clocks, env), `alloc` (literals and allocating
methods), `spawn`, `ffi` (extern, plugins, pointers, slices). Functions are found
by name, so two functions with one name share one row. Associativity and `unit`
being an identity are not checked. The input is cut into at most `4 * workers`
chunks (capped at 128), one task each; each element costs a closure call and a
result slot.

## 11. Modules and packages

Every `.brat` file is a module. Top-level functions, structs, enums, traits,
`let` and `const` are private unless marked `pub`. `import math.vec2` makes
`vec2.dot(...)` available, and `dot(...)` too when only one imported module has
that export. Two exports of one name make the bare name `ambiguous unqualified
name`; the qualified name always works. `pub use other.helper` re-exports a
name without duplicating it.

`import a.b` looks, in order, relative to the importing file (`a/b.brat`), in
`vendor/` next to the entry file or at the nearest parent holding `brat.lock`, and
for a `std.` path in `lang/std` (or `$BRAT_STDLIB`). `..` outside those roots is
refused. A file is loaded once and flattened into the program under mangled
names; unused functions are pruned before emission. Its top-level statements run
where the first `import` that reaches it sits. Modules may import each other,
but a cycle in which two or more have top-level statements is `import cycle`.

A private type may share a name with another module's private type. A `pub` type
and a type in the entry file share one namespace, and a second declaration is
refused.

A sibling `circle.bri` locks the public surface:

```brat
struct Circle { r: f64 }
fn area(c: Circle) -> f64
```

When it exists, only what it lists is visible, and a missing declaration or a
mismatched field, parameter or return type fails loading. `brat api` prints a
module's interface and `brat api --diff old.bri new.bri` calls the change
`none`, `minor` (exports added) or `major` (exports removed or retyped; exit
status non-zero).

Packages are `.tar.gz` archives vendored into `./vendor/` and pinned by SHA-256
in `brat.lock`. There is no registry. `brat pkg add` takes a local file, an HTTPS
URL, `github.com/owner/repo@ref`, or a name resolved against a static JSON
index (`$BRAT_INDEX`, default `./brat-index.json`, constraints such as
`>=1.0,<2.0` compared as dotted integers). Archives are capped at 16 MiB and
checked before extraction; the swap into `vendor/` and `brat.lock` is atomic and
rolls back on failure. More than 64 packages in a graph, cycles and
case-insensitive path collisions are rejected. Hostile paths in archives (`..`,
absolute, links, device names) are rejected. `brat pkg publish owner/name@ver
file.brat` copies the file under `.brat-packages/` beside the index and records
its digest. A package with `brat.pkg.json` may carry `c_sources` and `c_headers`;
`pkg add` compiles them, checks the `extern` declarations against the DWARF of
the result and writes a `.bratbind` manifest so users do not need
`--unsafe-ffi`. `brat pkg` refuses loopback, private and link-local addresses
unless `BRAT_PKG_ALLOW_INTERNAL=1`.

## 12. C interop

An `extern fn` is a plain C call. A wrong prototype corrupts the process, so
`build`, `run`, `dist` and `emit-c` refuse a program that calls C until its
declarations are checked against a header (`--header`), an object (`--object`) or
a `.bratbind` manifest. `--unsafe-ffi` skips the check.

```brat
extern fn puts(s: str) -> i32
extern "libm.so.6" { extern fn sin(x: f64) -> f64 }
extern struct Point { x: i64, y: f64 }
extern packed struct WireHdr { kind: u8, len: i32 }
extern union Payload { iv: i64, fv: f64 }
```

Types at the boundary: `i8 u8 i16 u16 i32 u32 i64 u64 usize`, `f32 f64`, `bool`,
`str` (`const char *`), `ptr` (`void *`), `ptr[T]` (`T *`), `extern struct`,
`extern union`, `fn(...) -> T`, `none`, and variadic tails `..ptr`, `..i64`,
`..f64`, `..StructName`. `size_t`, `ssize_t`, `intptr_t`, `int8_t`..`uint64_t`,
`short`, `float`, `double` and `_Bool` map to the type of the same width. C `long`
is 8 bytes on Linux and macOS and 4 on Windows, so spell the width. A narrow
integer argument is range-checked before the call and a narrow result is
extended to `i64`. A `u64` or `usize` result above `i64` max raises
`ffi: result of f does not fit i64`. `f32` narrows in and widens out.

Checks: against a header, the parameter count, the variadic tail, integer against
float, `str` against `const char *` (never a writable `char *`) and callback
signatures. The emitted C has a `_Static_assert` on the size of every `extern
struct` and the offset of every field. Against an object (`--object`, repeatable;
`.o .a .so .dylib .dll`) the symbol table and DWARF v2 to v5 are read without
loading the file. A built binary carries its declarations, layouts and the
header's SHA-256 in a `BRATFFI1` section that survives `strip`;
`brat ffi prog.brat --header api.h --bin ./prog` reports a header that changed.
Raw `#ifdef` in headers is rejected unless `--preprocess` is given.

Pointer ownership is declared, since headers do not carry it. `-> move ptr`
returns something the program must free or return on every path;
`move p: ptr` takes ownership; `-> ptr borrows(p)` returns a view that ends at
its last read and may not outlive `p`. A `move ptr` never freed is
`leaked owned pointer`; a second `free(move p)` or a read after it is
`use of moved`. `&x` at a `ptr[T]` parameter passes a slot of exactly the width of
`T` for C to write; `x` must be `let mut` and `f(&x, &x)` is refused.

A BRAT string passed to a `str` parameter is a `const char *` valid for the call.
A `str` result is copied and checked for UTF-8, and `NULL` raises.
`str_from_ptr(p, n)` reads a given length. `ptr_of_str(s)` is the address of the
bytes; returning `ptr_of_str(local)` is refused. A string of 14 bytes or less has
no buffer of its own, so it is copied into a pool that is never freed, capped by
`BRAT_PIN_BUDGET_BYTES` (default 64 MiB, `0` for no cap). The pool also holds
strings returned to C from an `export fn` or callback and written with
`ptr_write_str`.

`slice_of_ptr(p, len, kind)` wraps C memory without a copy for kind `"u8"`,
`"i32"`, `"i64"`, `"f32"`, `"f64"`; `slice_of_struct` gives a read-only window.
Slices have their own type and run-time tag, reject plain vectors, and check
bounds and value ranges on `slice_get` and `slice_set`. `ptr_read_struct` and
`ptr_write_struct` copy `extern struct` values; `p[i]` indexes `ptr[Node]`.
`errno` after a return type turns a `NULL` (or `-1` on `i32`, `i64`) into a
catchable error carrying `strerror(errno)`.

Effects after a return type: `writes(p)` tells the race check that the call
mutates memory behind `p`; `reads(p)` likewise; `pure` and `nothrow` become
`__attribute__((const/pure))` and `nothrow` in the C. Contradictions (`pure
writes(p)`, `pure` with `errno` or `move`) are rejected. Callbacks are passed as
a string naming a BRAT function (`0` for `NULL`, `-1` for sentinels such as
`SQLITE_TRANSIENT`); the emitter writes a typed wrapper including struct by
value. Callback parameters take `thread(same)` (default) or `thread(any)`, which
rejects callbacks that touch globals, and `reenter(yes)` (default) or
`reenter(no)`; unless `reenter(no)` is declared, a callback that calls back into
the same library is rejected.

`export fn` with `build --shared` produces a library for C callers
(`brat_plugin_abi_v1`). At run time `lib_open(path)`, `lib_sym(h, name)`,
`call(sym, "i64(i64,i64)", ...)` and `lib_close(h)` load libraries with `dlopen`
or `LoadLibraryW`. `call` checks BRAT arguments against the literal signature and
never against C; a wrong signature is undefined behaviour. `lib_close` waits for
in-flight calls on other threads. `brat bindgen header.h` writes checked `extern`
declarations plus a `.bratbind` manifest, from a C header or a Rust source, and
with `--lang` the bindings of Python, Go or Rust.

## 13. Built-ins

Available without `import`.

| Call | Answer |
|---|---|
| `print(a, ...)`, `eprint(a, ...)` | values to stdout or stderr, space-separated, newline after |
| `len(x)` | code points, items or keys |
| `str(x)` | the text `print` writes |
| `i64(x)`, `f64(x)`, `chr(n)`, `ord(s)` | conversions of section 3 |
| `assert(c)`, `assert(c, msg)` | raises `assert failed` or `msg` |
| `raise(x)`, `exit(code)` | section 7; end the program with that status |
| `args()`, `args_bytes()` | command-line arguments without the program name |
| `unwrap(x)`, `unwrap_or(x, d)` | payload of `Ok`/`Some`; raises or falls back on `Err`/`None` |
| `is_ok is_err is_some is_none is_int is_float is_str is_bool is_vec is_map` | tests |
| `own(x)` | heap copy of an arena value |
| `chan(cap)`, `join_all()`, `sleep_ms(ms)` | section 10 |
| `time_ms()`, `mono_ns()` | epoch milliseconds; monotonic nanoseconds |
| `env_get(name)`, `env_get_bytes(name)` | environment, filtered, section 15 |
| `read_file`, `write_file`, `append_file` | `Ok(text)` / `Ok(bytes written)` or `Err(message)`; confined to the program directory |
| `re_match(t, p)`, `re_find`, `re_captures`, `re_replace(t, p, with)` | regex, see below |
| `sql_open`, `proc_run` | the primitives under `std.sqlite` and `std.proc` |

Strings are never changed in place; every method answers a new value. Indices
count code points.

`s.split(sep)` (empty pieces kept; `s.split()` splits on whitespace runs),
`split_once(sep)` (`[l, r]` or `None`), `lines()`, `chars()`, `trim()`, `lower()`,
`upper()` (Unicode case mapping, `"ß".upper()` is `SS`; table version by
`BRAT_CASE_MAP_VERSION`, 1500 or 1600), `starts_with`, `ends_with`, `contains`,
`index_of(t)`, `replace(old, new)`, `repeat(n)`, `slice(a, b)` (negative counts
from the end, out of range is clipped), `parse_int()`, `parse_float()`,
`copy()`. `parse_int` rejects overflow (`number out of range`) and anything but
an optionally signed decimal (`not a number`).

Vectors: `push(x)` (new length), `pop()` (`None` if empty), `ins(i, x)`, `del(i)`
(raises outside the vector), `swap(i, j)`, `first()`, `last()`, `slice(a, b)`,
`rev()`, `copy()` (shallow), `sort()` (numbers by value, strings by code point,
vectors item by item, in place), `sort_by(key)` (stable, in place), `join(sep)`,
`sum()`, `min()`, `max()`, `pos(x)`, `enumerate()`, `zip(w)`, `chunks(n)`,
`map(f)`, `filter(f)`, `any(f)`, `all(f)`, `find(f)`, `fold(init, f)`.

Maps: `get(k)` (value or `None`), `get_or(k, d)`, `has(k)`, `set(k, x)`,
`del(k)` (`true` if present), `keys()`, `vals()`, `items()` (`[[k, v], ...]`),
`copy()`.

Option and Result: `unwrap()`, `unwrap_or(d)`, `is_ok()`, `is_err()`,
`is_some()`, `is_none()`. Channels: `send(x)`, `recv()`, `close()`.

Regular expressions are an NFA matcher with ECMAScript behaviour: every repeat
(`*`, `+`, `?`, `{m,n}`) stops taking empty iterations beyond its minimum.
After an empty match, `re_replace` advances one character. A `+` over a body that
can match the empty string is compiled as `{1,}` and copies the body, and nested
copies multiply: at 13 nested levels the pattern no longer fits in 65,536
instructions and is rejected with `bad regex pattern`; 12 levels work.

`brat check` counts the arguments of a built-in method (`"abc".chars(1)` is
``method `chars` wants 0 args``) and of the callback it takes. With an unknown
receiver the same mistake is a run-time error.

## 14. Standard library

Twelve modules in `lang/std/`, each with a `.bri` contract. Everything that can
fail returns `Result`. Paths and files are confined to the program directory
unless `BRAT_FILES=1`.

- `std.json`: `parse(s)` (RFC 8259, written in C), `stringify(v)`,
  `stringify_indent(v, n)`, `get_path(v, "a.b")`, `get_str`, `get_int`,
  `get_bool` with fallbacks.
- `std.http`: client `get`, `get_ca`, `get_follow`, `post_json`, `request`,
  `request_ex`, `request_headers`, `request_tls_ca`, keep-alive
  (`open_keep_alive`, `request_keep_alive`, `get_keep_alive`, `close_keep_alive`);
  server `listen`, `accept_request`, `serve_once`, `serve_keep_alive`,
  `read_request`, `respond`, `respond_text`, `respond_json`; helpers
  `parse_url`, `parse_query`, `encode_query`, `encode_query_component`,
  `decode_query_component`, `parse_request`, `format_response`, `status_text`.
  HTTP/1.1 and HTTPS.
- `std.sqlite`: `open`, `open_memory`, `close`, `exec`, `query(db, sql, params)`
  (a vector of maps), `query_one`, `scalar_int`. Parameters are bound, and the
  database must lie under the program directory; `ATTACH`, `VACUUM INTO`,
  `load_extension` and `PRAGMA`s that reach out are refused.
- `std.crypto`: `sha256`, `sha256_hex`, `hmac_sha256`, `hmac_sha256_hex`,
  `constant_time_eq`, and `rand_bytes`, `rand_hex` from the OS generator.
- `std.fs`: `exists`, `is_file`, `is_dir`, `file_size`, `mkdir_all`, `list_dir`,
  `rename`, `remove`, `remove_dir`, `read_or`, `read_lines`, `write_lines`,
  `append_text`, `write_atomic` (crash-safe), `open_read`, `read_line`, `close`,
  `stdin_line`.
- `std.path`: pure string work: `is_abs`, `join`, `dir`, `base`, `ext`, `stem`,
  `with_ext`, `norm`, `rel`.
- `std.bytes`: byte vectors (`vec[i64]` with items `0..255`): `read`, `write`,
  `from_str`, `to_str`, `eq`, `starts_with`, `concat`, `slice`, `index_of`,
  `to_hex`, `from_hex`, `to_base64`, `from_base64`.
- `std.cli`: `has_flag`, `opt`, `opt_int`, `positional`, `subcommand`,
  `subcommand_args`, all on an argv vector.
- `std.csv`: RFC 4180 `parse` and `dump`.
- `std.time`: `now_ms`, `now_mono_ns`, `unix_sec`, `sleep`, calendar math
  (`is_leap_year`, `days_in_month`, `days_from_civil`, `civil_from_days`,
  `day_of_week`), `format_iso8601_utc`, `parse_iso8601_utc`,
  `format_duration_ms`.
- `std.env`: `get`, `get_bytes`, `get_or`, `has`, `flag`. Names that look like
  secrets are denied by a list of common words (`SECRET`, `KEY`, `TOKEN`, `PASS`,
  `PASSWORD`, `CREDENTIAL`, `PRIVATE`); it misses others such as `ADMIN_PWD` or
  `GH_PAT`. For a strict
  setup use `BRAT_ENV_ALLOW`.
- `std.proc`: `run`, `run_timeout`, `status`, `output`. `execve` without a shell,
  off unless `BRAT_EXEC=1`, narrowed by `BRAT_EXEC_ALLOW`.

## 15. Command line

`make` builds `lang/cxx/bin/brat-cxx` and links it as `bin/brat`.

| Command | What it does |
|---|---|
| `brat check [--json] f.brat` | parse, load modules, check types and ownership; no C compiler |
| `brat run [-O0\|-O1\|-O2] [-g] [--trace-lines] [--mem SIZE] [ffi flags] f.brat [-- args]` | check, compile (cached), run. `--mem 16M` caps the address space |
| `brat build [-O..] [-g] [--static\|--dynamic] [--shared] [--link FLAG] [--target T] [--trace-lines] [--mem SIZE] [ffi flags] f.brat [-o out]` | standalone binary or shared library; `-g` emits `#line` maps and DWARF back to `.brat` |
| `brat dist [--target T[,T]] f.brat [-o dir]` | one build per target triple |
| `brat emit-c [-O..] [-g] f.brat [-o out.c]` | the generated C11 |
| `brat new name [--kind service\|tool]` | scaffold a project |
| `brat ffi [--json] [--preprocess] [-I d] [-D K=V] [--target t] [--abi-matrix] [--header h] [--object o] f.brat` | verify `extern` declarations |
| `brat bindgen h [...] [--lang brat\|python\|go\|rust] [-o out]` | generate bindings |
| `brat fmt [--check\|--stdout] files` | formatter; `--check` exits 1 on a file that needs it |
| `brat test [-j N] [--filter s] paths` | run `test_*.brat` files in parallel |
| `brat pkg add\|install\|verify\|list\|update\|publish` | packages |
| `brat deps [--dot\|--json] f.brat` | import graph |
| `brat api [--json] f.brat`, `brat api --diff a.bri b.bri` | interfaces |
| `brat doc [-o out.md\|out.html] f.brat` | API docs from signatures and doc comments |
| `brat bundle dir` | copy compiler, runtime headers, `lang/std` and a launcher |
| `brat explain [--json] CODE` | worked example for a diagnostic code |
| `brat mcp` | MCP tool server on stdio |

`-I`, `-D`, `--abi-matrix` belong to `ffi`; `bindgen` takes `-I`, `-D`,
`--target`; `build` and `dist` take `--target`, `run` does not.

Environment:

| Variable | Effect |
|---|---|
| `BRAT_CC` | C compiler (default `cc`) |
| `BRAT_CC_TIMEOUT_MS` | limit for one C compile, `1..3600000`, default 120000 |
| `BRAT_CACHE` | cache directory for `run` binaries and precompiled headers |
| `BRAT_NATIVE_CACHE_DISABLE=1` | skip the `run` cache (cold builds) |
| `BRAT_NO_PCH=1` | no precompiled `crt.h` |
| `BRAT_STDLIB` | where `import std.*` looks |
| `BRAT_INDEX` | package index path or URL |
| `BRAT_PKG_ALLOW_INTERNAL=1` | let `pkg` reach private addresses |
| `BRAT_CASE_MAP_VERSION` | `1500` (Unicode 15) or `1600` |
| `BRAT_MOVE_RT=0` | emit without ownership drops, to bisect; leaks on purpose |
| `BRAT_FILES=1` | lift confinement of files and SQLite to the program directory |
| `BRAT_EXEC=1` | allow `proc_run`; `BRAT_EXEC_ALLOW` is a colon-separated allowlist; `BRAT_PROC_TIMEOUT_MS` a default timeout |
| `BRAT_ENV_ALLOW`, `BRAT_ENV_DENY_ALL=1` | which variables `env_get` shows |
| `BRAT_RECURSION_BUDGET` | call depth cap, `1..1000000`, default 2000 |
| `BRAT_PIN_BUDGET_BYTES` | FFI string pool cap |
| `BRAT_THREADS` | worker threads, at most 32 |
| `BRAT_TRACE` | `0` no line in unhandled errors, `1` always |

## 16. Diagnostics

`brat check --json` prints code, severity, line, column, message, hint and fix.
`brat explain E0382` prints a runnable example.

| Code | Meaning |
|---|---|
| `E0382` | use of moved value |
| `E0499` | law of exclusivity |
| `E0502` | container mutated while iterated, or borrow conflict, or `v.push(v)` |
| `E0505` | move while an alias is read later |
| `E0507` | move out of a borrowed parameter |
| `E0515` | borrowed reference escapes via `return` or out of an `arena` |
| `E0596` | mutation of an immutable binding |
| `B0101` | undeclared name (with a spelling suggestion) |
| `B0521` | borrowed value escapes via `spawn` |
| `B0522` | data race between `spawn` tasks |
| `B0530` | plugin symbol used after `lib_close` |
| `B0531` | plugin signature mismatch |
| `B0000` | other check errors, such as duplicate definitions |
| `P0001` | syntax error, non-exhaustive `match` |
| `T0001` | type or arity mismatch, `arena` escape |
| `F0001` | unverified or inconsistent FFI declaration |
| `W0001` | unused variable (prefix with `_`) |
| `W0002` | `let mut` never mutated |
| `W0003` | unused `import` |
| `W0004` | `{...}` in a string stayed literal text |

## 17. Limits

Numbers.
- Integers wrap; see section 3. `"9223372036854775808".parse_int()` is
  `Err('number out of range')`.
- Call depth is 2000 frames, `main` included, then `recursion too deep`, which a
  `try` can catch. On Linux, macOS and Windows 8+ the same error is raised when
  less than 256 KiB of stack is left. `print`, `==`, `<` and `own` walk nested
  values under a 2000-level cap.
- `chan(cap)` caps at 1,048,576.

Source nesting. The parser refuses a block, a parenthesized expression, a pattern
or a type nested 200 levels, and an expression tree more than 1000 levels tall
(`expression tree too deep`). A run of unary operators counts as parenthesis
nesting. A chain `1 + 1 + ...` reaches the tree limit at about 1000 operators, an
`else if` chain at about 500, a `match` at about 1000 arms. A `match` arm without
braces counts as a block. Every pass is recursive and these bounds keep it inside
an 8 MiB stack; with a 1 MiB stack, deep but legal input can still crash `check`.

Representation. A value is 16 bytes: a tag byte, then either up to 14 inline
UTF-8 bytes or an 8-byte payload (integer, double, or pointer to a heap object
with a reference count). Reference counts are plain increments until threads or
dynamic plugins turn on `BRAT_CRT_MT`. Generics are erased to these slots;
`vec[i64]` and `vec[f64]` are specialised and a local non-escaping struct is split
at `-O2`. Strings longer than 14 bytes are on the heap; `s = s + x` grows in place
when `s` has one owner.

Compile time. The runtime is C headers compiled into each program, minus the
subsystems the program does not use. A cold `build -O2` of an empty `main` takes
about 0.85 s. Build time grows linearly with the locals of a function up to a few
hundred (400 heap-string locals: 4.7 s). Beyond that the compiler is quadratic in
the locals of one function, the functions of one file and the arguments of one
call: at 4,000 of them `check` takes about a second and `emit-c` up to six, and
an argument list is quadratic in the size of the C it emits. `run` caches the
binary keyed on the compiler, environment, emitted C, runtime, flags and linked
libraries.

Speed. Median of 5 on Linux x86-64 (AMD EPYC 7763, GCC 13.3.0 `-O2`, Go 1.27.3,
CPython 3.14.2); rows under 0.1 s move by up to 20%. `make bench` reproduces it.

| Workload | C | Go | BRAT | CPython |
|---|---:|---:|---:|---:|
| `int_loop(100M)` | 0.126 s | 0.129 s | 0.126 s | 16.795 s |
| `vec3_sra(50M)` | 0.134 s | 0.155 s | 0.141 s | 90.569 s |
| `fib(35)` | 0.024 s | 0.055 s | 0.050 s | 1.167 s |
| `str_append(200k)` | 0.014 s | 0.015 s | 0.031 s | 0.057 s |
| `dyn_records(100k)` | n/a | 0.017 s | 0.020 s | 0.047 s |
| `json_roundtrip(5k)` | n/a | 0.039 s | 0.010 s | 0.067 s |

Typed integer and float code is the loop `gcc` would get from C; a recursive one
also counts frames and checks the stack floor every 64 calls, which is the gap in
`fib`. Code that builds strings and maps is slower than Go. JSON is fast because
`std.json` is C.

Platforms. CI runs every test on Linux x86-64 (GCC, Clang, plus an
ASan/UBSan/LSan build), and the front end, checker, module, header and `bundle`
tests on macOS arm64 and Windows x86-64 (MinGW-w64). Process and socket tests are
Linux only. Big-endian and 32-bit Windows are unsupported.

Isolation. File access under the program directory (`O_NOFOLLOW`), the secret
name filter on the environment, and `proc_run` being off keep a script from
hurting itself. They are not a sandbox against hostile code.

## 18. Implementation

One implementation: a C++20 compiler (`lang/cxx/src/`, no libraries) and a C11
runtime of headers (`lang/engine/crt.h`, `lang/engine/crt/`). The compiler is not
self-hosted.

```text
.brat / .bri
  lexer.cpp, parser.cpp          tokens, AST, spans
  module.cpp, driver_pkg.cpp     imports, .bri, brat.lock
  check.cpp                      gradual types, traits, exhaustiveness
  borrow.cpp, capability.cpp,    moves, borrows, arenas, race and effect rules
    caps.cpp, parfor.cpp
  ffi_cdecl.cpp, ffi_object.cpp  C headers, ELF/Mach-O/PE symbols and DWARF
  ir.cpp                         scalar replacement of structs, range, division
                                 and reference-count elision (at -O2)
  emit.cpp                       C11 in two passes
  cc / gcc / clang / $BRAT_CC
```

Emission goes in two passes. The first lowers functions, closures, traits, enums
and method tables and records which runtime entry points and literals are used.
The second writes `#define BRAT_CRT_MASK`, `#include "crt.h"`, the literals and
forward declarations, so unused subsystems (HTTP and TLS, SQLite, regex, plugins,
worker pool, `par for`) are removed by the preprocessor. `crt.h` includes
`core.h`, `ops_str.h`, `conc.h`, `sql_proc.h`, `net_tls.h`.

BRAT structs lower to C structs of 16-byte fields unless split; `extern struct`
keeps the C layout and is asserted. Errors travel in a thread-local value
(`verr_pending`, `verr_take`) checked across calls, with no `setjmp` and no
exceptions across C frames. `borrow.cpp` is intra-procedural; the race and
effect passes build a summary per function (what it writes, reads, and which
parameters it returns).

`brat fmt`, `test`, `pkg`, `bindgen` and `mcp` run in the same binary on
the same parser and checker. The tests are in `lang/tests/` and run with
`python3 lang/tests/run_all.py`; `test_agreement.py` runs the programs in
`lang/tests/corpus/agreement.json`.

## 19. Known gaps

These are things the checker or the language does not do. Most are decisions,
some are debts.

- Ownership does not follow aliases across calls beyond `return p` and
  `return p.field` where the field is known to be a heap value (section 8).
  A function that returns a container holding a parameter, or a deeper path,
  gives the caller a second name the checker cannot see.
- A closure kept in a struct field hides what it writes from the race check, and
  so does one handed to a function whose spawn is not a plain call statement.
- C that does more than its declaration says (a write through a `ptr` without
  `writes(p)`, a pointer kept past the call without `move p: ptr`) is not caught.
- `move p.f` under `--no-check` is not caught at run time; `move x` is.
- Reference cycles built across functions leak.
- Arena values stored outside by a called function are copied, not rejected.
- Generics are erased; there are no trait objects, macros, async, unsigned types
  or `**`.
- A named function is not a value.
- Compile time is quadratic for very large functions, files and argument lists.
- Parsing and checking recurse; a 1 MiB stack can be exhausted by legal input of
  about the nesting limits.
- No package registry, no cycle collector, no green threads.

Not planned: lifetime annotations, a tracing garbage collector, an async runtime.
