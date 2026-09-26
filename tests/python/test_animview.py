"""The animation viewer (lmranim): source tracking of shapes, loading a chosen
Anim class, re-importing sibling modules on rebuild, the viewer page, its error
page, the editor bridge and the watch list."""

import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lemur.anim import mobject  # noqa: E402
from lemur.animview import AnimViewer  # noqa: E402
from lemur.emit import svg  # noqa: E402

TWO = textwrap.dedent("""\
    from lemur.anim import Anim, Circle, Square, Create, FadeIn, LEFT, RIGHT
    from helper import RADIUS


    class First(Anim):
        def build(self):
            c = Circle(radius=RADIUS).shift(LEFT)
            self.play(Create(c))
            self.next()
            s = Square(1.0).shift(RIGHT)
            self.play(FadeIn(s))
            self.next()


    class Second(Anim):
        def build(self):
            self.play(Create(Square(2.0)))
            self.next()
    """)


class ViewerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="lmranim-test-"))
        self.mod = self.dir / "two.py"
        self.mod.write_text(TWO, encoding="utf-8")
        (self.dir / "helper.py").write_text("RADIUS = 1.0\n", encoding="utf-8")
        (self.dir / "field.glsl").write_text("// shader\n", encoding="utf-8")

    def line_of(self, needle: str) -> int:
        return next(i for i, ln in enumerate(TWO.splitlines(), 1) if needle in ln)

    # -- loading ------------------------------------------------------------------

    def test_class_is_chosen_by_name_and_last_wins_otherwise(self):
        first = svg._load_anim(str(self.mod), "First")
        self.assertEqual(len(first["beats"]), 2)
        last = svg._load_anim(str(self.mod))
        self.assertEqual(len(last["beats"]), 1)                 # Second, defined last
        with self.assertRaisesRegex(ValueError, "have: First, Second"):
            svg._load_anim(str(self.mod), "Third")

    def test_sibling_modules_are_reimported(self):
        def circle():
            return svg._load_anim(str(self.mod), "First")["nodes"][0]["d"]
        before = circle()
        (self.dir / "helper.py").write_text("RADIUS = 2.0\n", encoding="utf-8")   # same size, same second
        self.assertNotEqual(before, circle())

    def test_source_tracking_is_off_unless_asked(self):
        ir = svg._load_anim(str(self.mod), "First")
        self.assertTrue(all("at" not in n for n in ir["nodes"]))
        mobject.TRACK_SOURCE = True
        try:
            ir = svg._load_anim(str(self.mod), "First")
        finally:
            mobject.TRACK_SOURCE = False
        at = [n.get("at") for n in ir["nodes"]]
        self.assertEqual(at[0], [str(self.mod), self.line_of("Circle(")])
        self.assertEqual(at[1], [str(self.mod), self.line_of("Square(1.0)")])

    # -- the viewer ----------------------------------------------------------------

    def viewer(self, **kw) -> AnimViewer:
        v = AnimViewer(self.mod, cls_name="First", **kw)
        v.publish = lambda event: None
        return v

    def test_page_carries_the_view_and_the_chrome(self):
        v = self.viewer()
        self.assertTrue(v.build())
        page = v.page
        self.assertIn("window.LMR_VIEW = ", page)
        self.assertIn("#av-bar", page)                           # animview.css
        self.assertIn(f"{self.line_of('Circle(')}]", page)        # node sources
        self.assertIn('"beats": [', page)
        self.assertFalse(mobject.TRACK_SOURCE)                    # switched back off

    def test_a_failing_module_gives_a_linked_error_page(self):
        self.mod.write_text(TWO.replace("self.next()\n", "1 / 0\n", 1), encoding="utf-8")
        v = self.viewer()
        self.assertFalse(v.build())
        self.assertIn("ZeroDivisionError", v.page)
        self.assertIn(f'data-file="{self.mod}"', v.page)
        self.assertIn("EventSource", v.page)                     # recovers by itself

    def test_editor_opens_only_files_of_the_animation(self):
        v = self.viewer()
        v.build()
        self.assertEqual(v.open_in_editor(str(self.mod), 7), f"{self.mod}:7")
        self.assertTrue(v.open_in_editor("/etc/passwd", 1).startswith("refused"))

    def test_editor_command_is_templated(self):
        out = self.dir / "opened.txt"
        v = self.viewer(editor=f"sh -c 'echo {{file}}:{{line}} > {out}'")
        v.build()
        v.open_in_editor(str(self.mod), 12)
        for _ in range(50):
            if out.exists() and out.read_text().strip():
                break
            time.sleep(0.05)
        self.assertEqual(out.read_text().strip(), f"{self.mod}:12")

    def test_watch_list_covers_the_folder_and_imports(self):
        v = self.viewer()
        v.build()
        names = {p.name for p in v.watched()}
        self.assertTrue({"two.py", "helper.py", "field.glsl"} <= names)
        self.assertFalse(any("site-packages" in p.parts for p in v.watched()))


class DeckWatchTest(unittest.TestCase):
    def test_deck_watch_covers_modules_shaders_and_images(self):
        from lemur.devserver import DeckBuilder
        d = Path(tempfile.mkdtemp(prefix="lmrwatch-test-"))
        for name in ("deck.lmr", "anim.py", "f.glsl", "k.wgsl", "fig.png", "out.html"):
            (d / name).write_text("", encoding="utf-8")
        b = DeckBuilder.__new__(DeckBuilder)
        b.source, b.style = d / "deck.lmr", None
        names = {p.name for p in b.watched_files()}
        self.assertEqual(names, {"deck.lmr", "anim.py", "f.glsl", "k.wgsl", "fig.png"})


if __name__ == "__main__":
    unittest.main()
