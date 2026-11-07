"""Pilot: generate a data-driven binary search HyperFrames HTML from validated input.

Reads a fixture JSON file, validates it against the bounded schema, computes
binary search steps, and renders the trusted HTML template with the data
safely injected as JSON. No raw HTML, JavaScript, paths, or shell commands
can reach the template.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from binary_search import compute_result
from escape import escape_html
from schema import SchemaError, validate_binary_search_data

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "src" / "template.html"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "renders"


def load_fixture(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_binary_search_data(validated: dict) -> dict:
    """Build the JSON payload injected into the template.

    Only primitive types (str, bool, int, list) — no HTML, no JS, no paths.
    """
    result = compute_result(validated["array"], validated["target"])
    return {
        "array": result["array"],
        "target": result["target"],
        "steps": result["steps"],
        "found": result["found"],
        "found_index": result["found_index"],
        "case_label": escape_html(validated["case_label"]),
    }


def render_html(bs_data: dict, output_path: Path) -> None:
    """Inject binary search data into the template and write the output HTML."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(bs_data, ensure_ascii=False)
    marker = '<script type="application/json" id="search-data"></script>'
    replacement = f'<script type="application/json" id="search-data">{data_json}</script>'
    if marker not in template:
        raise RuntimeError("template missing search-data marker")
    html = template.replace(marker, replacement, 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def run(fixture_path: Path, output_name: str, output_dir: Path | None = None) -> dict:
    """Full pilot: load, validate, compute, render. Returns computation result.

    If output_dir is provided, the HTML is written there instead of the
    default OUTPUT_DIR.
    """
    raw = load_fixture(fixture_path)
    validated = validate_binary_search_data(raw)
    bs_data = build_binary_search_data(validated)
    out_dir = output_dir if output_dir is not None else OUTPUT_DIR
    out_path = out_dir / output_name
    render_html(bs_data, out_path)
    return bs_data


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python binary_search_pilot.py <fixture.json> <output.html>", file=sys.stderr)
        sys.exit(2)
    fixture = Path(sys.argv[1])
    output = Path(sys.argv[2])
    bs_data = run(fixture, output.name)
    print(json.dumps(bs_data, indent=2))
