# Braindead test runner for lemur.  `make` (no target) lists what's available.
#
# The JavaScript integration tests drive a real browser; override its path with
#   make javascript CHROME=/path/to/chrome
CHROME ?= /usr/bin/google-chrome-stable

.PHONY: all python javascript test examples docs install

all:
	@echo "Usage: make <target>"
	@echo
	@echo "  python       run the Python parser/emitter tests (tests/python)"
	@echo "  javascript   run the JavaScript runtime tests (tests/js; jsdom + Chrome)"
	@echo "  test         run both"
	@echo "  examples     build every examples/ deck to build/examples/ (needs the svg extra)"
	@echo "  docs         build the HTML documentation to build/docs/ (needs the docs extra)"
	@echo "  install      (re)install the JavaScript test dependencies"

python:
	python3 -m unittest discover -s tests/python

# Build every standalone example with the build-time SVG emitter. The
# corporate/custom-templates decks carry a style.py next to them, so lmr2svg
# picks it up automatically — no extra flags.
examples:
	@mkdir -p build/examples
	@for d in formatting math lists tables figures code columns environments annotations references transitions animation animation3d anim-science anim-calculus anim-3d plots parallel-transport tangent-space tangent-space-illustrated optimal-transport live-shaders compute corporate custom-templates; do \
		echo "  $$d"; python3 lmr2svg.py examples/$$d/deck.lmr -o build/examples/$$d.html || exit 1; \
	done
	@echo "  lecture";         python3 lmr2svg.py examples/lecture/master.lmr -o build/examples/lecture.html || exit 1
	@echo "built -> build/examples/"

# The documentation (Sphinx + Furo + MyST). Its live examples are built with
# lmr2svg while the docs build. SPHINX defaults to a docs virtualenv if present.
SPHINX ?= $(if $(wildcard .venv-docs/bin/sphinx-build),.venv-docs/bin/sphinx-build,sphinx-build)
docs:
	$(SPHINX) -b html -q docs build/docs

javascript:
	@test -d tests/js/node_modules || (cd tests/js && npm install)
	cd tests/js && CHROME=$(CHROME) npm test

test: python javascript

install:
	cd tests/js && npm install
