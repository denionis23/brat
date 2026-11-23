# BRAT

[![CI](https://github.com/denionis23/brat/actions/workflows/ci.yml/badge.svg)](https://github.com/denionis23/brat/actions/workflows/ci.yml)

BRAT compiles to C11. You get one native binary and no garbage collector, which
suits command-line tools and glue around C libraries.

Ownership is checked inside a single function. Across calls values are
reference counted, so there are `move`, `ref` and `mut` and a checker that
rejects use after move, but no lifetimes in signatures.

```brat run
fn count_words(text: str) {
  let mut seen = {}
  for w in text.lower().split() {
    seen[w] = seen.get_or(w, 0) + 1
  }
  return seen
}

fn main() -> i64 {
  let seen = count_words("The cat saw the other cat")
  for w in seen.keys() {
    print("{w}: {seen[w]}")
  }
  return 0
}
```

```output
the: 2
cat: 2
saw: 1
other: 1
```

Use after move is caught:

```brat check
fn consume(buf: move str) {
  print(buf)
}

fn main() -> i64 {
  let payload = "once"
  consume(move payload)
  print(payload)
  return 0
}
```

```diagnostics
example.brat: 1 error(s), 0 warning(s)
example.brat:8: error: use of moved `payload` (hint: the value was moved; use a copy or re-bind)
  |   print(payload)
example.brat:7: note: `payload` moved here
  |   consume(move payload)
example.brat: 0 type error(s)
```

The check stops at the function boundary, so it proves less than Rust does. Two
functions can still build a reference cycle between them, and it leaks. What the
checker covers and what it misses is in the [spec](lang/spec/SPEC.md#8-ownership).

## Build

You need `make`, a C++20 compiler and a C11 compiler. Python 3 is only used by
the tests and the benchmark script.

```sh
git clone https://github.com/denionis23/brat.git && cd brat
make -j4
printf 'print(40 + 2)\n' > hello.brat
./bin/brat run hello.brat
```

Other commands: `check`, `emit-c`, `build -O2 hello.brat -o hello`.

## Docs

The whole language, the tools and the known gaps are in [the spec](lang/spec/SPEC.md).
Programs to start from are in [examples](examples/README.md).

## Speed

`make bench` builds and times these from source. Median of 5 runs, Linux x86-64
(AMD EPYC 7763, GCC 13.3.0 `-O2`, Go 1.27.3, CPython 3.14.2). Rows under 0.1 s
move by up to 20% between runs.

| Workload | C (`gcc -O2`) | Go 1.27 | BRAT (`build -O2`) | CPython 3.14 |
|---|---:|---:|---:|---:|
| `int_loop(100M)` | 0.126 s | 0.129 s | 0.126 s | 16.795 s |
| `vec3_sra(50M)` | 0.134 s | 0.155 s | 0.141 s | 90.569 s |
| `fib(35)` | 0.024 s | 0.055 s | 0.050 s | 1.167 s |
| `str_append(200k)` | 0.014 s | 0.015 s | 0.031 s | 0.057 s |
| `dyn_records(100k)` | n/a | 0.017 s | 0.020 s | 0.047 s |
| `json_roundtrip(5k)` | n/a | 0.039 s | 0.010 s | 0.067 s |

Typed integer and float code becomes plain C loops. String and map heavy code is
slower than Go, and `fib` pays for the recursion check that turns a stack
overflow into a catchable error. The JSON row is fast because `std.json` is C.

## Not for

Kernels or bare metal (the output needs libc and libm), programs where a
reference cycle must never leak, tight generic code (generics are type-erased,
except `vec[i64]` and `vec[f64]`), unsigned arithmetic (every integer is a
wrapping `i64`), and running code you don't trust. File access is confined to the
program directory, which catches mistakes but is not a sandbox.

## About

Most of the code was written by an AI model. I decide what the language does and
what gets merged. It is experimental and has one maintainer. CI runs on Linux
x86-64 (GCC, Clang, ASan, UBSan), macOS arm64 and Windows x86-64 (MinGW-w64).

```text
lang/cxx/src/    compiler, C++20
lang/engine/     runtime, C11 headers
lang/std/        standard library
lang/examples/   small programs, one feature each
lang/tests/      tests
```

[Security](SECURITY.md), [contributing](CONTRIBUTING.md), [license](LICENSE) (Apache-2.0).
