"""The tests must not share Manim's text cache.

Manim caches every rendered text as an SVG under ``<media_dir>/texts``, keyed
by the text and the style -- but not by the process. Two test workers that
render the same string at the same time write the same file, and one of them
can read it half written: the text comes out with the wrong size and the
geometry tests fail at random.

The proof is a race that needs several processes: eight of them rendering the
same string into one media directory ended in
``xml.etree.ElementTree.ParseError: no element found``. Every process
therefore gets its own ``media_dir`` (see ``tests/conftest.py``).
"""
import os


def test_every_process_has_its_own_text_cache():
    """The cache has to belong to this process alone."""
    from manim import config

    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    text_dir = str(config.get_dir("text_dir"))

    assert worker in text_dir, text_dir
