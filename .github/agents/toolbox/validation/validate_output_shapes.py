#!/usr/bin/env python3
"""Validate agent outputs for shape and semantic consistency.

Checks included:
- JSON structural conformance against templates
- required output file artifact existence
- semantic integrity across metadata JSON, Mermaid ERD, and Excel workbook
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


TEMPLATE_TO_OUTPUT = {
    "source_analyzer_output.template.json": "metadata/source_analyzer_output.json",
    "data_modeler_output.template.json": "metadata/data_modeler_output.json",
    "sql_mapping_output.template.json": "metadata/sql_mapping_output.json",
}

REQUIRED_OUTPUT_FILES = [
    "files/data_model_diagram.mmd",
    "files/sql_mapping_output.xlsx",
]

SOURCE_METADATA_PATH = Path("metadata/source_analyzer_output.json")
MODEL_METADATA_PATH = Path("metadata/data_modeler_output.json")
MAPPING_METADATA_PATH = Path("metadata/sql_mapping_output.json")
MMD_PATH = Path("files/data_model_diagram.mmd")
XLSX_PATH = Path("files/sql_mapping_output.xlsx")

REQUIRED_XLSX_SHEETS = {
    "mappings",
    "summary",
    "coverage",
    "quality_controls",
    "assumptions",
    "open_risks",
}


@dataclass
class ValidationError:
    path: str
    message: str


def table_name_to_entity(table_name: str) -> str:
    return table_name.upper()


def expected_dimension_for_fk(fk_column: str) -> str:
    if fk_column == "date_key":
        return "dim_calendar"
    if not fk_column.endswith("_key"):
        return ""
    return f"dim_{fk_column[:-4]}"


def kind_of(value: Any) -> str:
    """Normalize Python values to coarse JSON kinds."""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "scalar"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_shape(template: Any, actual: Any, path: str = "$") -> list[ValidationError]:
    errors: list[ValidationError] = []

    template_kind = kind_of(template)
    actual_kind = kind_of(actual)

    if template_kind != actual_kind:
        errors.append(
            ValidationError(path=path, message=f"kind mismatch: expected {template_kind}, got {actual_kind}")
        )
        return errors

    if isinstance(template, dict):
        for key, template_val in template.items():
            child_path = f"{path}.{key}"
            if key not in actual:
                errors.append(ValidationError(path=child_path, message="missing required key"))
                continue
            errors.extend(validate_shape(template_val, actual[key], child_path))
        return errors

    if isinstance(template, list):
        # Empty template list only constrains kind=array.
        if not template:
            return errors

        if not actual:
            # Allow empty actual arrays, but note that inner shape cannot be verified.
            return errors

        exemplar = template[0]
        for idx, item in enumerate(actual):
            errors.extend(validate_shape(exemplar, item, f"{path}[{idx}]"))
        return errors

    # Scalars: no strict type enforcement (template often uses "string" placeholders).
    return errors


def iter_template_pairs(templates_dir: Path, outputs_dir: Path) -> Iterable[tuple[Path, Path]]:
    for template_name, output_name in TEMPLATE_TO_OUTPUT.items():
        yield templates_dir / template_name, outputs_dir / output_name


def validate_required_files(outputs_dir: Path) -> int:
    missing = 0
    print("\nValidating: required file artifacts")
    for relative_path in REQUIRED_OUTPUT_FILES:
        artifact_path = outputs_dir / relative_path
        if artifact_path.exists():
            print(f"  PASS: found {relative_path}")
        else:
            missing += 1
            print(f"  FAIL: missing {relative_path}")
    return missing


def extract_mmd_entities(mmd_text: str) -> set[str]:
    return set(re.findall(r"^\s*([A-Z0-9_]+)\s*\{", mmd_text, flags=re.MULTILINE))


def extract_mmd_relationship_pairs(mmd_text: str) -> set[tuple[str, str]]:
    pattern = r"^\s*([A-Z0-9_]+)\s+\|\|--o\{\s+([A-Z0-9_]+)\s*:\s*[a-zA-Z0-9_]+"
    matches = re.findall(pattern, mmd_text, flags=re.MULTILINE)
    return {(left, right) for left, right in matches}


def get_xlsx_sheet_names(xlsx_path: Path) -> set[str]:
    with zipfile.ZipFile(xlsx_path, "r") as archive:
        workbook_xml = archive.read("xl/workbook.xml")

    root = ET.fromstring(workbook_xml)
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = root.findall("main:sheets/main:sheet", ns)
    return {sheet.attrib.get("name", "") for sheet in sheets}


def validate_semantics(outputs_dir: Path) -> int:
    errors = 0
    print("\nValidating: semantic consistency")

    source_metadata = load_json(outputs_dir / SOURCE_METADATA_PATH)
    model_metadata = load_json(outputs_dir / MODEL_METADATA_PATH)
    mapping_metadata = load_json(outputs_dir / MAPPING_METADATA_PATH)

    mmd_text = (outputs_dir / MMD_PATH).read_text(encoding="utf-8")
    if "erDiagram" not in mmd_text:
        errors += 1
        print("  FAIL: files/data_model_diagram.mmd missing erDiagram declaration")
    else:
        print("  PASS: Mermaid erDiagram declaration found")

    mmd_entities = extract_mmd_entities(mmd_text)
    mmd_pairs = extract_mmd_relationship_pairs(mmd_text)

    fact_tables = model_metadata.get("schema", {}).get("fact_tables", [])
    dim_tables = model_metadata.get("schema", {}).get("dimension_tables", [])
    model_table_names = {t.get("name", "") for t in fact_tables + dim_tables}
    expected_entities = {table_name_to_entity(name) for name in model_table_names if name}

    missing_entities = expected_entities - mmd_entities
    if missing_entities:
        errors += len(missing_entities)
        print(f"  FAIL: Mermaid missing entities {sorted(missing_entities)}")
    else:
        print("  PASS: Mermaid contains all modeled entities")

    expected_pairs: set[tuple[str, str]] = set()
    for fact in fact_tables:
        fact_name = fact.get("name", "")
        if not fact_name:
            continue
        fact_entity = table_name_to_entity(fact_name)
        for col in fact.get("columns", []):
            if col.get("key_type") != "FK":
                continue
            dim_name = expected_dimension_for_fk(col.get("name", ""))
            if dim_name and dim_name in model_table_names:
                expected_pairs.add((table_name_to_entity(dim_name), fact_entity))

    missing_pairs = expected_pairs - mmd_pairs
    if missing_pairs:
        errors += len(missing_pairs)
        print(f"  FAIL: Mermaid missing FK relationships {sorted(missing_pairs)}")
    else:
        print("  PASS: Mermaid includes expected FK relationships")

    try:
        sheet_names = get_xlsx_sheet_names(outputs_dir / XLSX_PATH)
        missing_sheets = REQUIRED_XLSX_SHEETS - sheet_names
        if missing_sheets:
            errors += len(missing_sheets)
            print(f"  FAIL: Excel missing required sheets {sorted(missing_sheets)}")
        else:
            print("  PASS: Excel includes all required sheets")
    except Exception as exc:  # pragma: no cover
        errors += 1
        print(f"  FAIL: Could not inspect Excel workbook sheets -> {exc}")

    source_columns_by_table = {
        table.get("table_name", ""): {col.get("name", "") for col in table.get("columns", [])}
        for table in source_metadata.get("tables", [])
    }
    model_columns_by_table = {
        table.get("name", ""): {col.get("name", "") for col in table.get("columns", [])}
        for table in fact_tables + dim_tables
    }

    mappings = mapping_metadata.get("mappings", [])
    mapping_errors = 0
    distinct_target_columns: set[tuple[str, str]] = set()
    for idx, mapping in enumerate(mappings):
        source_table = mapping.get("source_table", "")
        source_column = mapping.get("source_column", "")
        target_table = mapping.get("target_table", "")
        target_column = mapping.get("target_column", "")
        mapping_type = mapping.get("mapping_type", "")
        join_context = mapping.get("join_context", {}) or {}

        if source_table not in source_columns_by_table or source_column not in source_columns_by_table[source_table]:
            mapping_errors += 1
            print(f"  FAIL: mappings[{idx}] invalid source {source_table}.{source_column}")
        if target_table not in model_columns_by_table or target_column not in model_columns_by_table[target_table]:
            mapping_errors += 1
            print(f"  FAIL: mappings[{idx}] invalid target {target_table}.{target_column}")

        if mapping_type == "LOOKUP":
            if not join_context.get("required"):
                mapping_errors += 1
                print(f"  FAIL: mappings[{idx}] LOOKUP must set join_context.required=true")
            if not join_context.get("join_to"):
                mapping_errors += 1
                print(f"  FAIL: mappings[{idx}] LOOKUP missing join_context.join_to")
            if not join_context.get("join_condition"):
                mapping_errors += 1
                print(f"  FAIL: mappings[{idx}] LOOKUP missing join_context.join_condition")

        distinct_target_columns.add((target_table, target_column))

    if mapping_errors == 0:
        print("  PASS: Mapping source/target lineage references are valid")
    errors += mapping_errors

    coverage = mapping_metadata.get("coverage", {})
    mapped_count = int(coverage.get("mapped_target_columns", 0) or 0)
    total_count = int(coverage.get("total_target_columns", 0) or 0)
    unmapped = coverage.get("unmapped_target_columns", []) or []
    unmapped_count = len(unmapped)
    distinct_count = len(distinct_target_columns)

    if mapped_count != distinct_count:
        errors += 1
        print(
            "  FAIL: coverage.mapped_target_columns "
            f"({mapped_count}) does not match distinct mapped targets ({distinct_count})"
        )
    else:
        print("  PASS: coverage.mapped_target_columns matches mapping targets")

    if total_count != mapped_count + unmapped_count:
        errors += 1
        print(
            "  FAIL: coverage.total_target_columns does not equal mapped+unmapped "
            f"({total_count} vs {mapped_count + unmapped_count})"
        )
    else:
        print("  PASS: coverage totals are internally consistent")

    return errors


def validate_all(templates_dir: Path, outputs_dir: Path) -> int:
    total_errors = 0

    for template_path, output_path in iter_template_pairs(templates_dir, outputs_dir):
        print(f"\nValidating: {output_path.name}")

        if not template_path.exists():
            total_errors += 1
            print(f"  ERROR: template not found -> {template_path}")
            continue

        if not output_path.exists():
            total_errors += 1
            print(f"  ERROR: output not found -> {output_path}")
            continue

        try:
            template_json = load_json(template_path)
            output_json = load_json(output_path)
        except Exception as exc:  # pragma: no cover
            total_errors += 1
            print(f"  ERROR: failed to parse JSON -> {exc}")
            continue

        errors = validate_shape(template_json, output_json)
        if errors:
            print(f"  FAIL: {len(errors)} shape issue(s)")
            for err in errors:
                print(f"    - {err.path}: {err.message}")
            total_errors += len(errors)
        else:
            print("  PASS: shape conforms to template")

    total_errors += validate_required_files(outputs_dir)
    if total_errors == 0:
        total_errors += validate_semantics(outputs_dir)
    else:
        print("\nSkipping semantic checks due to prior shape/file failures")

    return total_errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate output JSON shape against templates")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    templates_dir = repo_root / ".github" / "agents" / "templates"
    outputs_dir = repo_root / "data" / "outputs"

    print("=" * 68)
    print("Template Shape Validation")
    print("=" * 68)
    print(f"Templates: {templates_dir}")
    print(f"Outputs:   {outputs_dir}")

    error_count = validate_all(templates_dir, outputs_dir)

    print("\n" + "=" * 68)
    if error_count:
        print(f"RESULT: FAILED ({error_count} issue(s) found)")
        return 1

    print("RESULT: PASSED (all outputs conform)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
