``lemur.anim``: animations
==========================

The library behind ``!anim``. See :doc:`../figures/animations`,
:doc:`../figures/3d` and :doc:`../figures/illustrated` for a guided tour; this
page lists the API.

.. module:: lemur.anim

The animation
-------------

.. autoclass:: lemur.anim.scene.Anim
   :members: enabled, build, play, add, remove, wait, next, bring_to_front, bring_to_back, play_many
   :exclude-members: recording

.. autoclass:: lemur.anim.mobject.ValueTracker
   :members: get_value, set_value, increment_value

Shapes
------

Every shape derives from :class:`~lemur.anim.mobject.VShape`, which carries the
methods for moving, styling and grouping (``shift``, ``move_to``, ``scale``,
``rotate``, ``next_to``, ``set_color``, ``set_fill``, ``set_stroke``,
``add_updater``, ``animate``, …).

.. automodule:: lemur.anim.shapes
   :members:
   :undoc-members:

Text and maths
--------------

.. automodule:: lemur.anim.text
   :members: Text, MarkupText, Tex, MathTex, Title, BulletList, Paragraph

Animations
----------

.. automodule:: lemur.anim.animation.creation
   :members:
   :undoc-members:

.. automodule:: lemur.anim.animation.transform
   :members:
   :undoc-members:

.. automodule:: lemur.anim.animation.indication
   :members:
   :undoc-members:

.. automodule:: lemur.anim.animation.base
   :members:
   :undoc-members:

3‑D views
---------

.. autoclass:: lemur.anim.three.View
   :members:

Legends and insets
------------------

.. autofunction:: lemur.anim.decorate.legend
.. autofunction:: lemur.anim.decorate.panel

Illustrated figures
-------------------

.. automodule:: lemur.anim.illustrate
   :members: Figure, Sphere, Palette, slerp, unit

Shapes and their methods
------------------------

.. autoclass:: lemur.anim.mobject.Shape
   :members:

.. autoclass:: lemur.anim.mobject.VShape
   :members:

.. autoclass:: lemur.anim.mobject.VGroup
