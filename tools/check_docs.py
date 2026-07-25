#!/usr/bin/env python3
"""Check the rocksdb:*/N calls in the docs against the -export lists.

Catches guides drifting away from the API: calls to functions that no longer
exist, calls with the wrong arity, and snippets that forgot the module prefix.

    python3 tools/check_docs.py

Exits non-zero when anything is found.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "src", "rocksdb.erl")
DOCS = ["README.md", "GETTING_STARTED.md", "CUSTOMIZED_BUILDS.md"]

FENCE = re.compile(r"^```+\s*(\w*)\s*$")
CALL = re.compile(r"\brocksdb:([a-z_][a-zA-Z0-9_]*)\s*(?=\()")
BARE = re.compile(r"(?<![:\w.])([a-z_][a-zA-Z0-9_]*)\s*(?=\()")


def exported(path):
    """{name: {arity, ...}} from every -export list in the module."""
    src = open(path).read()
    # drop comments so examples written in @doc tags do not leak in
    code = "\n".join(line.split("%")[0] for line in src.splitlines())
    out = {}
    for block in re.finditer(r"-export\(\s*\[(.*?)\]\s*\)\s*\.", code, re.S):
        for name, arity in re.findall(r"([a-z_][a-zA-Z0-9_]*)\s*/\s*(\d+)", block.group(1)):
            out.setdefault(name, set()).add(int(arity))
    return out


def count_args(text, i):
    """text[i] is '('. Return (arity, elided) counting top-level commas.

    arity is None when the parens are unbalanced, which happens in snippets
    that elide code. elided is True for a literal `(...)`.
    """
    depth = 0
    args = 0
    seen = False
    body = []
    while i < len(text):
        c = text[i]
        closing = c in ")]}" and depth == 1
        if depth >= 1:
            body.append(c)
            if c != "," and not closing and not c.isspace():
                seen = True
        if c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "$":
            i += 2
            continue
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                elided = "".join(body[:-1]).strip() == "..."
                return (args + 1 if seen else 0), elided
        elif depth == 1 and c == ",":
            args += 1
        i += 1
    return None, False


def snippets(path):
    """(first_line, text) for each fenced block in a markdown file."""
    out, cur, start, inside = [], [], 0, False
    for n, line in enumerate(open(path), 1):
        if FENCE.match(line.rstrip()):
            if inside:
                out.append((start, "".join(cur)))
                cur, inside = [], False
            else:
                inside, start = True, n + 1
            continue
        if inside:
            cur.append(line)
    return out


def line_of(text, offset, start):
    return start + text[:offset].count("\n")


def is_spec(text, offset):
    """True when offset sits on a -spec line, where a bare call is correct."""
    bol = text.rfind("\n", 0, offset) + 1
    return text[bol:offset].lstrip().startswith("-spec")


def main():
    exports = exported(SOURCE)
    files = [os.path.join(ROOT, f) for f in DOCS]
    files += sorted(glob.glob(os.path.join(ROOT, "guides", "*.md")))

    problems = []
    for path in files:
        rel = os.path.relpath(path, ROOT)
        for start, text in snippets(path):
            for m in CALL.finditer(text):
                name = m.group(1)
                arity, elided = count_args(text, m.end())
                line = line_of(text, m.start(), start)
                if name not in exports:
                    problems.append((rel, line, f"rocksdb:{name} is not exported"))
                elif arity is not None and not elided and arity not in exports[name]:
                    wanted = " or ".join(f"{name}/{a}" for a in sorted(exports[name]))
                    problems.append(
                        (rel, line, f"rocksdb:{name}/{arity} does not exist, use {wanted}")
                    )
            for m in BARE.finditer(text):
                name = m.group(1)
                if name not in exports or is_spec(text, m.start()):
                    continue
                arity, elided = count_args(text, m.end())
                if arity is None or elided or arity not in exports[name]:
                    continue
                line = line_of(text, m.start(), start)
                problems.append((rel, line, f"{name}/{arity} is missing the rocksdb: prefix"))

    for rel, line, msg in problems:
        print(f"{rel}:{line}: {msg}")
    if problems:
        print(f"\n{len(problems)} problem(s) found in the docs")
        return 1
    print(f"docs ok: {len(files)} files checked against {len(exports)} exported names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
