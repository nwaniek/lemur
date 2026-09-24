"""Phase 0 (Plan-DisplayModel.md): the shared AST seam. lmrast is the contract
every emitter meets the parser at — version, node vocabulary, load/validate — and
`lemur.parser --ast` is the seam that lets the emitters consume the parser's output
without importing its internals."""
import contextlib
import glob
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # tests/python -> tests -> repo root
sys.path.insert(0, ROOT)

import lemur.ast as lmrast
from lemur import load_lines, Parser, deck_to_ast, main

DECKS = sorted(glob.glob(os.path.join(ROOT, "examples", "**", "*.lmr"), recursive=True)) + \
    [os.path.join(ROOT, "spec", "spec.lmr")]


def _example_ast():
    return deck_to_ast(Parser(load_lines(
        os.path.join(ROOT, "examples", "lecture", "master.lmr"))).parse())


def _all_types(node, out):
    """Collect every node 'type' string anywhere in an AST value."""
    if isinstance(node, dict):
        if isinstance(node.get("type"), str):
            out.add(node["type"])
        for v in node.values():
            _all_types(v, out)
    elif isinstance(node, list):
        for v in node:
            _all_types(v, out)
    return out


class TestLmrast(unittest.TestCase):
    def test_version_is_the_single_source_of_truth(self):
        # the parser stamps the AST with lmrast.AST_VERSION, and the schema agrees
        self.assertEqual(_example_ast()["astVersion"], lmrast.AST_VERSION)
        with open(os.path.join(ROOT, "spec", "ast.schema.json")) as fh:
            schema = json.load(fh)
        self.assertEqual(schema["properties"]["astVersion"]["const"],
                         lmrast.AST_VERSION)

    def test_loads_round_trip_and_validate(self):
        ast = _example_ast()
        got = lmrast.loads(lmrast.dumps(ast))     # serialize -> parse+validate
        self.assertEqual(got["astVersion"], lmrast.AST_VERSION)
        self.assertEqual(len(got["body"]), len(ast["body"]))

    def test_check_rejects_bad_version_and_shape(self):
        with self.assertRaises(lmrast.ASTError):
            lmrast.check({"astVersion": 999, "meta": {}, "body": []})
        with self.assertRaises(lmrast.ASTError):
            lmrast.check({"astVersion": lmrast.AST_VERSION, "meta": {}})  # no body
        with self.assertRaises(lmrast.ASTError):
            lmrast.check(["not", "an", "object"])

    def test_node_vocabulary_is_complete(self):
        # every node type the parser can emit (across all example decks) must be
        # in the declared vocabulary — a new node type that skips lmrast fails here
        vocab = lmrast.BLOCK_TYPES | lmrast.INLINE_TYPES
        seen = set()
        for path in DECKS:
            _all_types(deck_to_ast(Parser(load_lines(path)).parse()), seen)
        self.assertTrue(seen, "no node types collected")
        self.assertEqual(seen - vocab, set(),
                         f"node types missing from lmrast vocabulary: {seen - vocab}")

    def test_ast_cli_emits_valid_contract(self):
        # 'lemur.parser <deck> --ast' prints a version-checked AST and builds nothing
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([os.path.join(ROOT, "examples", "lecture", "master.lmr"), "--ast"])
        self.assertEqual(rc, 0)
        ast = lmrast.loads(buf.getvalue())        # parses + passes the version gate
        self.assertIn("body", ast)


if __name__ == "__main__":
    unittest.main()
