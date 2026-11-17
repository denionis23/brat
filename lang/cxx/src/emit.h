// The C backend: the whole program in one translation unit, the way
// `brat build` hands it to cc.
#pragma once

#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include "ast.h"
#include "ir.h"

namespace codegen {

struct EmitError : std::runtime_error {
    explicit EmitError(const std::string &m) : std::runtime_error(m) {}
};

// `prog` is a flattened module set; `base` is the directory `vbase_set` reports.
// `opt` selects optimization level (0 = baseline C emission, 1 = interval
// check elision, 2 = relational check elision + SRA). `proofs`, when non-null,
// records one entry per elided check. `no_c_symbol`, when non-null, receives a
// line for each `export fn` whose signature has no C form: such a function is
// an ordinary one in a program and has no symbol in a shared library.
std::string emit_program(const std::vector<StmtP> &prog, const std::string &base, int opt = 0,
                         std::vector<ir::Proof> *proofs = nullptr,
                         const std::string &target = "",
                         bool trace_lines = false,
                         bool debug_lines = false,
                         const std::string &root_file = "",
                         const std::map<const Stmt *, std::string> *stmt_files = nullptr,
                         const std::map<std::string, std::string> *fn_files = nullptr,
                         std::vector<std::string> *no_c_symbol = nullptr);

// Sorted, unique library names the program's `extern` blocks ask to link.
std::vector<std::string> extern_libs(const std::vector<StmtP> &prog);

}  // namespace codegen
