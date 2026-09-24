from lemur.anim import Anim, Circle, Square, Create, Transform, FadeIn, MathTex, RIGHT, LEFT, UP


class Hello(Anim):
    def build(self):
        c = Circle(radius=1.5, color="#2c69b0", stroke_width=6).shift(LEFT * 3)
        self.play(Create(c))
        self.next()                    # keypress 1 plays everything above

        self.play(c.animate.shift(RIGHT * 6))
        self.next()                    # keypress 2

        square = Square(3, color="#c0392b", stroke_width=6).shift(RIGHT * 3)
        self.play(Transform(c, square))
        label = MathTex(r"x \mapsto x^2", color="#c0392b").scale(1.6).next_to(c, UP)
        self.play(FadeIn(label))
        self.next()                    # keypress 3
