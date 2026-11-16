"""The native C++ frontend checks, emits and builds without Python."""
import _cxx
import _scratch

import hashlib
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "engine"))
TMP = _scratch.mkdtemp(prefix="brat-cxx-build-")
BIN = _cxx.build()


def write(path, source):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(source)
    return path


def run_build(*args):
    return subprocess.run([BIN, "build"] + list(args), capture_output=True, text=True,
                          timeout=300)


lib_dir = os.path.join(TMP, "lib")
os.makedirs(lib_dir)
write(os.path.join(lib_dir, "mathx.brat"),
      "pub fn square(x: i64) -> i64 { return x * x }\n")
source = write(os.path.join(TMP, "app with spaces.brat"),
               "import lib.mathx\nfn main() -> i64 {\n"
               "  print(lib.mathx.square(7))\n  return 0\n}\n")
exe = os.path.join(TMP, "app")
build = run_build(source, "-o", exe)
assert build.returncode == 0, build.stdout + build.stderr
run = subprocess.run([exe], capture_output=True, timeout=30)
assert run.returncode == 0 and run.stdout == b"49\n", (run.returncode, run.stdout, run.stderr)

# Two builds with different staging paths must produce byte-identical artifacts.
repeat_exe = os.path.join(TMP, "app-repeat")
repeat = run_build(source, "-o", repeat_exe)
assert repeat.returncode == 0, repeat.stdout + repeat.stderr
with open(exe, "rb") as f:
    first_hash = hashlib.sha256(f.read()).hexdigest()
with open(repeat_exe, "rb") as f:
    repeat_hash = hashlib.sha256(f.read()).hexdigest()
assert first_hash == repeat_hash, (first_hash, repeat_hash)

# A bundle contains the driver and runtime header in the layout the driver expects.
bundle = os.path.join(TMP, "release")
packed = subprocess.run([BIN, "bundle", bundle], capture_output=True, text=True,
                        timeout=30)
assert packed.returncode == 0, packed.stdout + packed.stderr
bundled_bin = os.path.join(bundle, "lang", "cxx", "bin", "brat-cxx")
assert os.path.isfile(bundled_bin)
assert os.path.isfile(os.path.join(bundle, "lang", "engine", "crt.h"))
bundled_exe = os.path.join(TMP, "bundled-app")
bundled_build = subprocess.run([bundled_bin, "build", source, "-o", bundled_exe],
                               capture_output=True, text=True, timeout=300)
assert bundled_build.returncode == 0, bundled_build.stdout + bundled_build.stderr
run = subprocess.run([bundled_exe], capture_output=True, timeout=30)
assert run.returncode == 0 and run.stdout == b"49\n", (
    run.returncode, run.stdout, run.stderr)

# The regular CLI delegates a fresh frontend build to the native command too.
wrapper_exe = os.path.join(TMP, "wrapper")
wrapped = subprocess.run(_cxx.cli_args("build", source, "-o", wrapper_exe),
                         capture_output=True, text=True, timeout=300)
assert wrapped.returncode == 0, wrapped.stdout + wrapped.stderr
run = subprocess.run([wrapper_exe], capture_output=True, timeout=30)
assert run.returncode == 0 and run.stdout == b"49\n", (run.returncode, run.stdout, run.stderr)

bad = write(os.path.join(TMP, "type-error.brat"),
            'fn main() -> i64 { return "not an integer" }\n')
refused = run_build(bad, "-o", os.path.join(TMP, "type-error"))
assert refused.returncode == 1 and "type error" in refused.stdout, (
    refused.returncode, refused.stdout, refused.stderr)
assert not os.path.exists(os.path.join(TMP, "type-error"))

bad = write(os.path.join(TMP, "move-error.brat"),
            'fn main() -> i64 {\n  let a = ["x"]\n  let b = move a\n'
            '  print(len(a))\n  return 0\n}\n')
refused = run_build(bad, "-o", os.path.join(TMP, "move-error"))
assert refused.returncode == 1 and "use of moved" in refused.stdout, (
    refused.returncode, refused.stdout, refused.stderr)
assert not os.path.exists(os.path.join(TMP, "move-error"))

mem = run_build(source, "-o", os.path.join(TMP, "mem"), "--mem", "16M")
assert mem.returncode == 0, mem.stdout + mem.stderr

# `brat-cxx run` is the product path with no Python in it: check, emit, link
# once into a content-addressed cache, exec. The cache must never serve a stale
# program, and the backend the user gets must behave like the -O0 build.
env = dict(os.environ, BRAT_CACHE=os.path.join(TMP, "cache"))


def run_native(path, *args):
    return subprocess.run([BIN, "run", path] + list(args), capture_output=True,
                          text=True, timeout=300, env=env)


RUN_CASES = {
    "prints": ('fn main() -> i64 {\n  print("ok")\n  return 0\n}\n', "ok\n", 0),
    "exit_code": ('fn main() -> i64 {\n  print("x")\n  return 3\n}\n', "x\n", 3),
    "args": ('fn main() -> i64 {\n  print(len(args()))\n  return 0\n}\n', "2\n", 0),
}
for name, (src, want, rc) in RUN_CASES.items():
    path = write(os.path.join(TMP, "run-%s.brat" % name), src)
    extra = ["--", "a", "b"] if name == "args" else []
    got = run_native(path, *extra)
    assert got.returncode == rc and got.stdout == want, (name, got.returncode, got.stdout, got.stderr)
    run_o0 = subprocess.run(_cxx.run_args(path, *(extra[1:])),
                            capture_output=True, text=True, timeout=300)
    assert run_o0.stdout == want, ("run_o0 disagrees", name, run_o0.stdout)

# A clean run says nothing but the program's own output.
assert ": 0 error(s)" not in run_native(write(os.path.join(TMP, "quiet.brat"),
                                             RUN_CASES["prints"][0])).stdout

# The cache key follows the emitted C: editing the source changes the answer,
# while another run of the same source keeps the same entry.
cached = write(os.path.join(TMP, "cached.brat"),
               'fn main() -> i64 {\n  print("one")\n  return 0\n}\n')
first = run_native(cached)
assert first.stdout == "one\n", first.stdout
again = run_native(cached)
assert again.stdout == "one\n", again.stdout
write(cached, 'fn main() -> i64 {\n  print("two")\n  return 0\n}\n')
assert run_native(cached).stdout == "two\n"


def run_entries():
    return sorted(f for f in os.listdir(os.path.join(TMP, "cache", "run")) if not f.endswith(".c"))


# One entry per case, one for `quiet.brat` and two for the versions of
# `cached.brat`. `quiet.brat` has the text of the `prints` case and still gets
# its own entry, because a runtime error names the file it happened in.
assert len(run_entries()) == len(RUN_CASES) + 3, run_entries()

# A custom compiler or search path can depend on the working directory, so
# that context gets a separate key for each directory. The default compiler
# shares the entry and still reports a path relative to the current directory.
context_vars = (
    "BRAT_CC", "CC", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH",
    "OBJC_INCLUDE_PATH", "COMPILER_PATH", "GCC_EXEC_PREFIX", "LIBRARY_PATH",
    "SDKROOT", "MACOSX_DEPLOYMENT_TARGET",
)
cwd_sensitive = any(name in env for name in context_vars) or env.get("BRAT_NATIVE_CACHE_DISABLE") == "1"
if not cwd_sensitive:
    for name in ("cc", "gcc", "clang"):
        compiler = shutil.which(name)
        if compiler:
            try:
                with open(compiler, "rb") as f:
                    prefix = f.read(2)
                    cwd_sensitive = len(prefix) != 2 or prefix == b"#!"
            except OSError:
                cwd_sensitive = True
            break

FAILS = 'fn main() -> i64 {\n  let v = [1]\n  print(v[3])\n  return 0\n}\n'
os.makedirs(os.path.join(TMP, "proj", "src"))
os.makedirs(os.path.join(TMP, "elsewhere"))
one = write(os.path.join(TMP, "proj", "src", "one.brat"), FAILS)
before = run_entries()
cwd_cases = ((os.path.join(TMP, "proj", "src"), "one.brat"),
             (os.path.join(TMP, "proj"), "src/one.brat"),
             (TMP, "proj/src/one.brat"))
for i, (cwd, shown) in enumerate(cwd_cases, 1):
    got = subprocess.run([BIN, "run", one], capture_output=True, text=True, timeout=300,
                         env=env, cwd=cwd)
    assert got.returncode == 1 and got.stderr == \
        "unhandled: Err('index out of range') at %s:3\n" % shown, (cwd, got.stderr)
    expected = len(before) + (i if cwd_sensitive else 1)
    assert len(run_entries()) == expected, (cwd, run_entries())
elsewhere = os.path.join(TMP, "elsewhere")
got = subprocess.run([BIN, "run", one], capture_output=True, text=True, timeout=300,
                     env=env, cwd=elsewhere)
full = got.stderr.strip().split(" at ")[-1]
assert got.returncode == 1 and full.endswith(":3") and os.path.isabs(full[:-2]) and os.path.samefile(full[:-2], one), got.stderr
expected = len(before) + (len(cwd_cases) + 1 if cwd_sensitive else 1)
assert len(run_entries()) == expected, run_entries()
entries = run_entries()
again = subprocess.run([BIN, "run", one], capture_output=True, text=True, timeout=300,
                       env=env, cwd=elsewhere)
assert again.returncode == 1 and again.stderr == got.stderr and run_entries() == entries

# The same text under another name is another program as far as its errors go.
two = write(os.path.join(TMP, "proj", "src", "two.brat"), FAILS)
got = subprocess.run([BIN, "run", two], capture_output=True, text=True, timeout=300,
                     env=env, cwd=os.path.join(TMP, "proj", "src"))
assert got.returncode == 1 and got.stderr == "unhandled: Err('index out of range') at two.brat:3\n", got.stderr
assert len(run_entries()) == len(entries) + 1, run_entries()

# Exercise the custom-compiler key even when the suite was started without one.
compiler = env.get("BRAT_CC") or env.get("CC") or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
assert compiler, "no C compiler found"
custom_env = dict(env, BRAT_CC=compiler)
custom = write(os.path.join(TMP, "proj", "src", "custom.brat"), FAILS)
before_custom = set(run_entries())
for i, (cwd, shown) in enumerate(((os.path.join(TMP, "proj", "src"), "custom.brat"),
                                  (os.path.join(TMP, "proj"), "src/custom.brat")), 1):
    got = subprocess.run([BIN, "run", custom], capture_output=True, text=True, timeout=300,
                         env=custom_env, cwd=cwd)
    assert got.returncode == 1 and got.stderr == \
        "unhandled: Err('index out of range') at %s:3\n" % shown, (cwd, got.stderr)
    assert len(set(run_entries()) - before_custom) == i, (cwd, run_entries())

# A program the checker refuses is refused before anything is compiled.
bad_run = write(os.path.join(TMP, "run-bad.brat"),
                'fn main() -> i64 {\n  let a = ["x"]\n  let b = move a\n'
                '  print(len(a))\n  return 0\n}\n')
refused_run = run_native(bad_run)
assert refused_run.returncode == 1 and "use of moved" in refused_run.stderr and refused_run.stdout == "", (
    refused_run.returncode, refused_run.stdout, refused_run.stderr)

print("CXX BUILD ALL GREEN (5 cases + native run)")
