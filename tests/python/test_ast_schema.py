"""Guards for the AST contract (spec/ast.schema.json), the parser<->emitter
boundary. The schema is the single source of truth for node types; these tests
keep it well-formed and keep the worked example conformant. When the parser
emits the versioned AST, its output is validated here too.

`jsonschema` is a dev-only convenience: where it is absent (e.g. a stdlib-only
run) the validation tests skip rather than fail, so the parser suite never gains
a hard dependency."""
import glob
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # tests/python -> tests -> repo root
sys.path.insert(0, ROOT)
SCHEMA = os.path.join(ROOT, "spec", "ast.schema.json")
EXAMPLE = os.path.join(ROOT, "spec", "ast-example.json")
DECKS = sorted(glob.glob(os.path.join(ROOT, "examples", "**", "*.lmr"), recursive=True)) + \
    [os.path.join(ROOT, "spec", "spec.lmr")]

try:
    from jsonschema import Draft202012Validator
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestAstSchema(unittest.TestCase):
    def test_schema_is_valid_json(self):
        schema = _load(SCHEMA)
        self.assertEqual(schema.get("astVersion", None) or
                         schema["properties"]["astVersion"]["const"], 1)

    def test_example_is_valid_json(self):
        self.assertEqual(_load(EXAMPLE)["astVersion"], 1)

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_schema_is_valid_draft202012(self):
        Draft202012Validator.check_schema(_load(SCHEMA))

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_example_validates_against_schema(self):
        validator = Draft202012Validator(_load(SCHEMA))
        errors = sorted(validator.iter_errors(_load(EXAMPLE)),
                        key=lambda e: list(e.path))
        self.assertEqual(
            errors, [],
            "example does not conform:\n" +
            "\n".join(f"  {list(e.path)}: {e.message}" for e in errors))

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_parser_output_conforms(self):
        """The parser is the primary producer of the contract: every example
        deck's emitted AST must validate against the schema."""
        from lemur import load_lines, Parser, deck_to_ast
        validator = Draft202012Validator(_load(SCHEMA))
        for path in DECKS:
            ast = deck_to_ast(Parser(load_lines(path)).parse())
            errors = sorted(validator.iter_errors(ast),
                            key=lambda e: list(e.path))
            self.assertEqual(
                errors, [],
                f"{os.path.basename(path)} AST does not conform:\n" +
                "\n".join(f"  {list(e.path)}: {e.message}" for e in errors))


if __name__ == "__main__":
    unittest.main()
