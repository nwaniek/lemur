``lemur.style``: designs and templates
=======================================

The API of a deck's ``style.py``. See :doc:`../design/style` and
:doc:`../design/templates` for a guided tour.

.. module:: lemur.style

Designs
-------

.. autoclass:: lemur.master.Style
   :no-members:

   Its fields are listed in :doc:`style-fields`.

.. autoclass:: lemur.master.Region

Templates
---------

.. autofunction:: lemur.emit.svg.register

.. autoclass:: lemur.emit.svg.Ctx
   :no-members:

Helpers
-------

.. autofunction:: lemur.emit.svg.line
.. autofunction:: lemur.emit.svg.flow
.. autofunction:: lemur.emit.svg.header
.. autofunction:: lemur.emit.svg.footer
.. autofunction:: lemur.emit.svg.logo
.. autofunction:: lemur.emit.svg.region
.. autofunction:: lemur.emit.svg.body_bottom

Built-in templates
------------------

Call these from your own template to extend rather than replace them.

.. autofunction:: lemur.emit.svg.content
.. autofunction:: lemur.emit.svg.cover
.. autofunction:: lemur.emit.svg.section

Drawing on a slide
------------------

``ctx.slide`` is the slide being drawn.

.. automethod:: lemur.render.svgdoc.Slide.add_rect
.. automethod:: lemur.render.svgdoc.Slide.add_image
.. automethod:: lemur.render.svgdoc.Slide.add_back
.. automethod:: lemur.render.svgdoc.Slide.add_overlay
