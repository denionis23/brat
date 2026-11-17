import _cxx
import _scratch
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = _scratch.mkdtemp(prefix="brat-qualified-")


def write(rel, src):
    path = os.path.join(TMP, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def run(path):
    return subprocess.run(_cxx.cli_args("run", "-O0", path),
                          capture_output=True, timeout=120)


def build_and_run(path, tag):
    exe = os.path.join(TMP, tag + ".exe")
    built = subprocess.run(_cxx.cli_args("build", path, "-o", exe),
                           capture_output=True, timeout=300)
    assert built.returncode == 0, (built.stdout + built.stderr).decode("utf-8", "replace")
    return subprocess.run([exe], capture_output=True, timeout=60)


def expect_both(path, tag, stdout):
    run_o0 = run(path)
    assert run_o0.returncode == 0 and run_o0.stdout == stdout, \
        "run_o0: rc=%d out=%r" % (run_o0.returncode, run_o0.stdout + run_o0.stderr)
    native = build_and_run(path, tag)
    assert native.returncode == 0 and native.stdout == stdout, \
        "native: rc=%d out=%r" % (native.returncode, native.stdout + native.stderr)


def expect_error(path, text):
    run_o0 = run(path)
    out = (run_o0.stdout + run_o0.stderr).decode("utf-8", "replace")
    assert run_o0.returncode != 0 and text in out, "run: rc=%d out=%r" % (run_o0.returncode, out)
    exe = os.path.join(TMP, "bad.exe")
    built = subprocess.run(_cxx.cli_args("build", path, "-o", exe),
                           capture_output=True, timeout=300)
    out = (built.stdout + built.stderr).decode("utf-8", "replace")
    assert built.returncode != 0 and text in out and not os.path.exists(exe), \
        "build: rc=%d out=%r" % (built.returncode, out)


def main():
    write("qualified/a/b.brat",
          "fn helper(x: i64) -> i64 { return x + 1 }\n"
          "pub fn f(x: i64) -> i64 { return helper(x) * 2 }\n")
    qualified = write("qualified/main.brat",
                      "import a.b\nfn main() -> i64 {\n"
                      "  print(b.f(20))\n  print(f(5))\n  return 0\n}\n")
    expect_both(qualified, "qualified", b"42\n12\n")
    print("modules qualified ok: qualified call and unique pub at -O0 and -O2")

    private = write("qualified/private.brat",
                    "import a.b\nfn main() -> i64 {\n"
                    "  print(b.helper(1))\n  return 0\n}\n")
    expect_error(private, "function `helper` is private")
    print("modules qualified ok: private function rejected by run and build")

    write("ambiguous/a.brat", 'pub fn name() -> str { return "A" }\n')
    write("ambiguous/b.brat", 'pub fn name() -> str { return "B" }\n')
    ambiguous = write("ambiguous/main.brat",
                      "import a\nimport b\nfn main() -> i64 {\n"
                      "  print(name())\n  return 0\n}\n")
    expect_error(ambiguous, "ambiguous unqualified name `name`")
    print("modules qualified ok: ambiguous unqualified name rejected by run and build")

    distinct = write("ambiguous/distinct.brat",
                     "import a\nimport b\nfn main() -> i64 {\n"
                     "  print(a.name())\n  print(b.name())\n  return 0\n}\n")
    expect_both(distinct, "distinct", b"A\nB\n")
    print("modules qualified ok: qualification disambiguates at -O0 and -O2")

    # `mod.NAME` reads an exported constant, also where the file has a `NAME`
    # of its own or two modules export one; what is not `pub const` stays out
    write("values/cfg.brat",
          "pub const LIMIT = 20\nconst STEP = 2\nlet names = [\"cfg\"]\n"
          "pub fn limit() -> i64 { return LIMIT * STEP + len(names) }\n")
    write("values/alt.brat", "pub const LIMIT = 5\n")
    consts = write("values/consts.brat",
                   "import cfg\nimport alt\nconst LIMIT = 7\nfn main() -> i64 {\n"
                   "  print(LIMIT, cfg.LIMIT, alt.LIMIT, cfg.LIMIT + alt.LIMIT, cfg.limit())\n"
                   "  return 0\n}\n")
    expect_both(consts, "consts", b"7 20 5 25 41\n")
    expect_error(write("values/private.brat",
                       "import cfg\nfn main() -> i64 {\n  print(cfg.names)\n  return 0\n}\n"),
                 "`names` is private in module `cfg`")
    expect_error(write("values/missing.brat",
                       "import cfg\nfn main() -> i64 {\n  print(cfg.NOPE)\n  return 0\n}\n"),
                 "module `cfg` has no `NOPE`")
    print("modules qualified ok: qualified constant, private binding and missing name")

    # an imported function is a callback under its qualified and its bare
    # name, a module passes its own, and a local of the same name is a local
    write("values/geo/shape.brat",
          "pub fn area(r: i64) -> i64 { return 3 * r * r }\n"
          "fn twice(x: i64) -> i64 { return x * 2 }\n"
          "pub fn doubled(v) { return v.map(twice) }\n")
    callbacks = write("values/callbacks.brat",
                      "import geo.shape\nstruct Box { area: i64 }\n"
                      "fn show(shape: Box) -> i64 { return shape.area }\n"
                      "fn main() -> i64 {\n"
                      "  print([1, 2].map(shape.area), [1, 2].map(geo.shape.area), [1, 2].map(area))\n"
                      "  print(shape.doubled([1, 2]), show(Box { area: 9 }))\n"
                      "  return 0\n}\n")
    expect_both(callbacks, "callbacks", b"[3, 12] [3, 12] [3, 12]\n[2, 4] 9\n")
    expect_error(write("values/private_fn.brat",
                       "import geo.shape\nfn main() -> i64 {\n"
                       "  print([1].map(shape.twice))\n  return 0\n}\n"),
                 "function `twice` is private in module `geo.shape`")
    print("modules qualified ok: imported function as a callback")

    print("MODULES QUALIFIED ALL GREEN (15 asserts)")


if __name__ == "__main__":
    main()
