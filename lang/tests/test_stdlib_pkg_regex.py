"""Standard-library modules, packages with C sources, the MCP server, and the regex engine."""
import _cxx
import _scratch
import http.server
import json
import os
import subprocess
import tarfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ENGINE = os.path.join(ROOT, "lang", "engine")
BIN = os.environ.get("BRAT_CXX") or _cxx.build()
TMP = _scratch.mkdtemp(prefix="brat-eco-")

# The all-stdlib program takes longer with an instrumented compiler.
COMPILER_TIMEOUT = 600

asserts = 0


def check(cond, msg):
    global asserts
    if not cond:
        raise AssertionError(msg)
    asserts += 1


# 1. Upgraded stdlib + {n,m} regex & captures/replace
#    (-O0 == ASan/LSan native, byte-identical C through both CLI doors)
class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/old":
            self.send_response(302)
            self.send_header("Location", "/chunked")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/chunked"):
            hdr_val = self.headers.get("X-Client", "none")
            c1 = ("hdr=" + hdr_val + ";").encode("utf-8")
            c2 = "привет!".encode("utf-8")
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Echo", "ok")
            self.end_headers()
            for part in (c1, c2):
                self.wfile.write(("%x\r\n" % len(part)).encode("ascii") + part + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    std_src = os.path.join(TMP, "std_regex.brat")
    with open(std_src, "w", encoding="utf-8") as f:
        f.write(f"""import std.bytes
import std.path
import std.fs
import std.cli
import std.json
import std.http

fn main() -> i64 {{
  // std.bytes: UTF-8, slice, index_of, Base64
  let bs = std.bytes.from_str("Hello, мир!")
  assert(unwrap(std.bytes.to_str(bs)) == "Hello, мир!")
  assert(std.bytes.index_of(bs, std.bytes.from_str("мир")) == 7)
  assert(unwrap(std.bytes.to_str(std.bytes.slice(bs, 0, 5))) == "Hello")
  let b64 = unwrap(std.bytes.to_base64(bs))
  assert(b64 == "SGVsbG8sINC80LjRgCE=")
  assert(unwrap(std.bytes.to_str(unwrap(std.bytes.from_base64(b64)))) == "Hello, мир!")
  assert(is_err(std.bytes.from_base64("bad===")))

  // std.path: with_ext, rel
  assert(std.path.with_ext("a/b/mod.brat", "bri") == "a/b/mod.bri")
  assert(std.path.with_ext("mod.brat", ".c") == "mod.c")
  assert(std.path.rel("/work/a/b", "/work/a/c/d.txt") == "../c/d.txt")
  assert(std.path.rel("src/sub", "src/sub") == ".")

  // std.fs: write_lines, write_atomic, remove
  let _wl = unwrap(std.fs.write_lines("lines.txt", ["alpha", "beta"]))
  assert(unwrap(std.fs.read_lines("lines.txt")) == ["alpha", "beta"])
  let _wa = unwrap(std.fs.write_atomic("atomic.txt", "v1"))
  let _wa2 = unwrap(std.fs.write_atomic("atomic.txt", "v2-atomic"))
  assert(std.fs.read_or("atomic.txt", "") == "v2-atomic")
  assert(!std.fs.exists("atomic.txt.brat.tmp"))
  let _rm = unwrap(std.fs.remove("lines.txt"))
  assert(!std.fs.exists("lines.txt"))

  // std.cli: --flag=bool, subcommand, subcommand_args
  let av = ["--color=false", "--jobs=4", "-v", "deploy", "--env=prod", "svc"]
  assert(!std.cli.has_flag(av, "--color"))
  assert(std.cli.has_flag(av, "--jobs"))
  assert(std.cli.has_flag(av, "-v"))
  assert(std.cli.subcommand(av, []) == "deploy")
  assert(std.cli.subcommand_args(av, []) == ["--env=prod", "svc"])

  // std.json: \\uXXXX + surrogate pair, stringify_indent, get_path, typed getters
  let raw_j = "{{\\"rocket\\": \\"\\\\uD83D\\\\uDE80\\", \\"euro\\": \\"\\\\u20AC\\", \\"cfg\\": {{\\"port\\": 8080, \\"tls\\": true}}, \\"tags\\": [\\"x\\", \\"y\\"]}}"
  let doc = unwrap(std.json.parse(raw_j))
  assert(std.json.get_str(doc, "rocket", "") == "🚀")
  assert(std.json.get_str(doc, "euro", "") == "€")
  assert(unwrap(std.json.get_path(doc, "cfg.port")) == 8080)
  assert(unwrap(std.json.get_path(doc, "tags.1")) == "y")
  assert(is_none(std.json.get_path(doc, "tags.9")))
  assert(std.json.get_int(doc.get("cfg"), "port", 0) == 8080)
  assert(std.json.get_bool(doc.get("cfg"), "tls", false))
  assert(is_err(std.json.parse("\\"\\\\uD800\\"")))
  let pretty = std.json.stringify_indent({{"a": [1, 2]}}, 2)
  assert(pretty.contains("\\n  \\"a\\": [\\n    1,"))

  // std.http: query encode/parse, request_ex custom headers + chunked, get_follow redirects
  let qs = std.http.encode_query({{"q": "hello мир", "p": "1"}})
  let pq = unwrap(std.http.parse_query("?" + qs))
  assert(pq.get("q") == "hello мир" && pq.get("p") == "1")
  let rx = unwrap(std.http.request_ex("GET", "http://127.0.0.1:{port}/chunked", {{"X-Client": "brat02"}}, ""))
  assert(rx.get("status") == 200)
  assert(rx.get("headers").get("x-echo") == "ok")
  assert(rx.get("body") == "hdr=brat02;привет!")
  let rf = unwrap(std.http.get_follow("http://127.0.0.1:{port}/old", 3))
  assert(rf.get("status") == 200 && rf.get("body") == "hdr=none;привет!")

  // bounded regex {{n,m}}, re_find, re_captures, re_replace
  assert(re_match("2026-11-01", "^\\\\d\\{{4\\}}-\\\\d\\{{2\\}}-\\\\d\\{{2\\}}$"))
  assert(!re_match("26-11-01", "^\\\\d\\{{4\\}}-\\\\d\\{{2\\}}-\\\\d\\{{2\\}}$"))
  assert(re_match("aaaa", "^a{{2,4}}$") && !re_match("aaaaa", "^a{{2,4}}$"))
  assert(re_match("aaaaa", "^a{{3,}}$") && !re_match("aa", "^a{{3,}}$"))
  assert(unwrap(re_find("id=abc-987!", "[a-z]+-\\\\d\\{{3\\}}")) == "abc-987")
  assert(is_none(re_find("nope", "\\\\d\\{{4\\}}")))
  let caps = unwrap(re_captures("2026-11-01", "(\\\\d\\{{4\\}})-(\\\\d\\{{2\\}})-(\\\\d\\{{2\\}})"))
  assert(caps == ["2026-11-01", "2026", "11", "01"])
  let rep = re_replace("2026-11-01 & 2027-01-05", "(\\\\d\\{{4\\}})-(\\\\d\\{{2\\}})-(\\\\d\\{{2\\}})", "$3/$2/$1 ($$)")
  assert(rep == "01/11/2026 ($) & 05/01/2027 ($)")
  // One rule for an iteration that takes no character: past the minimum of
  // the repeat it is dropped and the next alternative is tried. `+`, `?` and
  // a counted repeat took it and stopped, and found `` where `*` found `b`.
  assert(unwrap(re_find("b", "(a?|b)*")) == "b" && unwrap(re_find("b", "(a?|b)+")) == "b")
  assert(unwrap(re_find("b", "(a?|b)?")) == "b" && unwrap(re_find("b", "(a?|b)\\{{0,3\\}}")) == "b")
  assert(re_replace("b", "(a?|b)+", "-") == "--" && re_replace("b", "(a?|b)*", "-") == "--")
  assert(unwrap(re_find("b", "(|b)\\{{2\\}}")) == "" && re_match("", "^(a?)\\{{3\\}}$"))
  assert(unwrap(re_find("aab", "(a*)+b")) == "aab" && unwrap(re_find("aaa", "(a*)?")) == "aaa")
  // `+` over a body that can match nothing copies the body once, as a counted
  // repeat does. Nested, the copies multiply: twelve levels over `a?` fit the
  // 65,536 instructions of a pattern and fourteen are refused.
  let mut deep = "a?"
  for i in 0..12 {{
    deep = "(" + deep + ")+"
  }}
  assert(unwrap(re_find("aaab", deep)) == "aaa")
  let mut refused = ""
  try {{
    let got = re_find("aaab", "((" + deep + ")+)+")
  }} catch e {{
    refused = "{{e}}"
  }}
  assert(refused == "bad regex pattern")

  print("W2_STD_REGEX_OK")
  return 0
}}
""")

    emit_cx = subprocess.check_output([BIN, "emit-c", std_src], text=True, timeout=COMPILER_TIMEOUT)

    c_path = os.path.join(TMP, "std_regex.c")
    exe_path = os.path.join(TMP, "std_regex.asan")
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(emit_cx)
    comp = subprocess.run(
        ["gcc", "-std=gnu11", "-O1", "-g", "-fsanitize=address,undefined",
         f"-I{ENGINE}", c_path, "-o", exe_path, "-lm", "-lpthread"],
        capture_output=True, text=True, timeout=90,
    )
    check(comp.returncode == 0, "ASan compile failed: " + comp.stderr)

    ri = subprocess.run([BIN, "run", "-O0", std_src],
                        capture_output=True, text=True, cwd=TMP, timeout=COMPILER_TIMEOUT)
    rn = subprocess.run([exe_path], capture_output=True, text=True, cwd=TMP, timeout=60,
                        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1"})
    check(ri.returncode == 0 and ri.stdout == "W2_STD_REGEX_OK\n",
          f"run -O0 failed: {ri.returncode} {ri.stdout} {ri.stderr}")
    check(rn.returncode == 0 and rn.stdout == "W2_STD_REGEX_OK\n" and rn.stderr == "",
          f"native ASan failed: {rn.returncode} {rn.stdout} {rn.stderr}")
finally:
    srv.shutdown()
    srv.server_close()


# Zero-flag `c_sources` compilation in `brat pkg` + `.bratbind`
pkg_build_dir = os.path.join(TMP, "csrc_pkg_src")
os.makedirs(pkg_build_dir, exist_ok=True)
hdr_p = os.path.join(pkg_build_dir, "hashx.h")
c_p = os.path.join(pkg_build_dir, "hashx.c")
brat_p = os.path.join(pkg_build_dir, "hashx.brat")
bri_p = os.path.join(pkg_build_dir, "hashx.bri")
bind_p = os.path.join(pkg_build_dir, "hashx.bratbind")
manifest_p = os.path.join(pkg_build_dir, "brat.pkg.json")

with open(hdr_p, "w", encoding="utf-8") as f:
    f.write("#include <stdint.h>\nint64_t hashx_fold(int64_t a, int64_t b);\n")
with open(c_p, "w", encoding="utf-8") as f:
    f.write('#include "hashx.h"\nint64_t hashx_fold(int64_t a, int64_t b) { return (a * 31) + (b * 17) + 9; }\n')
with open(brat_p, "w", encoding="utf-8") as f:
    f.write("extern fn hashx_fold(a: i64, b: i64) -> i64;\npub fn fold(x: i64, y: i64) -> i64 {\n  return hashx_fold(x, y)\n}\n")
with open(bri_p, "w", encoding="utf-8") as f:
    f.write("fn fold(x: i64, y: i64) -> i64\n")
with open(manifest_p, "w", encoding="utf-8") as f:
    json.dump({"name": "hashx", "version": "0.2.0", "c_sources": ["hashx.c"]}, f)

eb = subprocess.run([BIN, "ffi", brat_p, "--header", hdr_p, "--emit-bind", bind_p],
                    capture_output=True, text=True, timeout=30)
check(eb.returncode == 0 and os.path.isfile(bind_p), "emit-bind failed: " + eb.stderr)

# Package contains only portable source + .bratbind - no precompiled .o.
tgz_p = os.path.join(TMP, "hashx-0.2.0.tar.gz")
with tarfile.open(tgz_p, "w:gz") as tf:
    for fn in ("brat.pkg.json", "hashx.h", "hashx.c", "hashx.brat", "hashx.bri", "hashx.bratbind"):
        tf.add(os.path.join(pkg_build_dir, fn), arcname=fn)

proj = os.path.join(TMP, "csrc_consumer")
os.makedirs(proj, exist_ok=True)
r_add = subprocess.run([BIN, "pkg", "add", "file://" + tgz_p],
                       capture_output=True, text=True, cwd=proj, timeout=60)
check(r_add.returncode == 0, "pkg add c_sources failed: " + r_add.stdout + r_add.stderr)

lock_data = json.loads(open(os.path.join(proj, "brat.lock"), encoding="utf-8").read())
check(lock_data[0].get("c_sources") == ["hashx/hashx.c"], f"c_sources not locked: {lock_data}")

app_p = os.path.join(proj, "app.brat")
with open(app_p, "w", encoding="utf-8") as f:
    f.write("import hashx.hashx\nfn main() -> i64 {\n  print(hashx.hashx.fold(10, 5))\n  return 0\n}\n")

exe_cx = os.path.join(proj, "app_cx")
# No --link, no --header, no --unsafe-ffi.
bcx = subprocess.run([BIN, "build", app_p, "-o", exe_cx],
                     capture_output=True, text=True, cwd=proj, timeout=60)
rcx = subprocess.run([BIN, "run", app_p],
                     capture_output=True, text=True, cwd=proj, timeout=60)
check(bcx.returncode == 0, "brat-cxx build zero-flag c_sources failed: " + bcx.stderr)
check(rcx.returncode == 0 and rcx.stdout == "404\n", f"brat-cxx run c_sources failed: {rcx.stdout} {rcx.stderr}")
check(subprocess.check_output([exe_cx], text=True) == "404\n", "exe_cx output mismatch")

# Tampering with a vendored C file must fail both `pkg verify` and `build`.
vendored_c = os.path.join(proj, "vendor", "hashx", "hashx.c")
orig_c = open(vendored_c, "rb").read()
with open(vendored_c, "ab") as f:
    f.write(b"\n/* tampered */\n")
tamper_cx = subprocess.run([BIN, "build", app_p, "-o", exe_cx],
                           capture_output=True, text=True, cwd=proj, timeout=30)
check(tamper_cx.returncode != 0 and "HASH MISMATCH" in tamper_cx.stderr,
      f"build missed tampered C source: {tamper_cx.stderr}")
open(vendored_c, "wb").write(orig_c)


# MCP new tools: brat_abi_matrix & brat_pkg_verify
mcp = subprocess.Popen([BIN, "mcp"], stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    for req in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "brat_abi_matrix", "arguments": {"path": brat_p, "header": hdr_p}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "brat_pkg_verify", "arguments": {"dir": proj}}},
    ):
        mcp.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
    mcp.stdin.flush()
    r1 = json.loads(mcp.stdout.readline().decode("utf-8"))
    r2 = json.loads(mcp.stdout.readline().decode("utf-8"))
    r3 = json.loads(mcp.stdout.readline().decode("utf-8"))
    check(r2["result"]["isError"] is False, f"MCP abi_matrix failed: {r2}")
    mat = json.loads(r2["result"]["content"][0]["text"])
    check(mat.get("ok") is True and len(mat.get("targets", [])) == 5, f"abi_matrix payload: {mat}")
    check(r3["result"]["isError"] is False, f"MCP pkg_verify failed: {r3}")
    ver_body = json.loads(r3["result"]["content"][0]["text"])
    check("verified 1 package(s)" in ver_body["stdout"], f"pkg_verify payload: {ver_body}")
finally:
    mcp.kill()
    mcp.wait()

print(f"ECOSYSTEM ALL GREEN ({asserts} asserts)")
