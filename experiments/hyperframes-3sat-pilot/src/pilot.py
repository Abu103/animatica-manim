"""Pilot: generate a data-driven 3-SAT HyperFrames HTML from validated fixtures.

Reads a fixture JSON file, validates it against the bounded schema, computes
Boolean truth values, and renders the trusted HTML template with the data
safely injected as JSON. No raw HTML, JavaScript, paths, or shell commands
can reach the template.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from escape import escape_html, format_case_label, format_literal_label, format_truth
from schema import evaluate_all, validate_pilot_data

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "src" / "template.html"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "renders"


def load_fixture(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_pilot_data(validated: dict) -> dict:
    """Build the JSON payload injected into the template.

    Only primitive types (str, bool, int) — no HTML, no JS, no paths.
    """
    evaluation = evaluate_all(validated)
    clause_forms = []
    for clause in validated["clauses"]:
        lit_labels = [
            format_literal_label(lit["var"], lit["negated"])
            for lit in clause["literals"]
        ]
        clause_forms.append({
            "id": clause["id"],
            "label": clause["label"],
            "rule": clause["rule"],
            "literals": [
                {
                    "var": lit["var"],
                    "negated": lit["negated"],
                    "label": format_literal_label(lit["var"], lit["negated"]),
                }
                for lit in clause["literals"]
            ],
        })

    return {
        "variables": validated["variables"],
        "clauses": clause_forms,
        "assignment": validated["assignment"],
        "case_label": format_case_label(validated["case_label"]),
        "evaluation": {
            "literal_values": evaluation["literal_values"],
            "clause_values": evaluation["clause_values"],
            "formula_value": evaluation["formula_value"],
        },
    }


def render_html(pilot_data: dict, output_path: Path) -> None:
    """Inject pilot data into the template and write the output HTML."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(pilot_data, ensure_ascii=False)
    marker = '<script type="application/json" id="pilot-data"></script>'
    replacement = f'<script type="application/json" id="pilot-data">{data_json}</script>'
    if marker not in template:
        raise RuntimeError("template missing pilot-data marker")
    html = template.replace(marker, replacement, 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def run(fixture_path: Path, output_name: str) -> dict:
    """Full pilot: load, validate, evaluate, render. Returns evaluation result."""
    raw = load_fixture(fixture_path)
    validated = validate_pilot_data(raw)
    pilot_data = build_pilot_data(validated)
    out_path = OUTPUT_DIR / output_name
    render_html(pilot_data, out_path)
    return pilot_data["evaluation"]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pilot.py <fixture.json> <output.html>", file=sys.stderr)
        sys.exit(2)
    fixture = Path(sys.argv[1])
    output = Path(sys.argv[2])
    eval_result = run(fixture, output.name)
    print(json.dumps(eval_result, indent=2))
