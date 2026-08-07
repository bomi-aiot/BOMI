"""Small, dependency-free OOXML reader for BOMI column-definition maintenance tools."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref)
    if not letters:
        return 0
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))
    return values


def _sheet_paths(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    result: list[tuple[str, str]] = []
    for sheet in workbook.find(f"{{{MAIN_NS}}}sheets") or []:
        relation_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = targets[relation_id].replace("\\", "/")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = f"xl/{target}"
        result.append((sheet.attrib["name"], target))
    return result


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{MAIN_NS}}}is")
        return "" if inline is None else "".join(node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    raw = "" if value is None or value.text is None else value.text
    if cell_type == "s" and raw:
        return shared[int(raw)]
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def read_workbook(path: Path) -> tuple[list[str], dict[str, list[list[str]]]]:
    """Return sheet order and rectangular row values for every worksheet."""
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet_paths = _sheet_paths(archive)
        sheets: dict[str, list[list[str]]] = {}
        for sheet_name, sheet_path in sheet_paths:
            root = ET.fromstring(archive.read(sheet_path))
            rows: list[list[str]] = []
            sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
            if sheet_data is None:
                sheets[sheet_name] = rows
                continue
            for row in sheet_data.findall(f"{{{MAIN_NS}}}row"):
                values: list[str] = []
                for cell in row.findall(f"{{{MAIN_NS}}}c"):
                    index = _column_index(cell.attrib.get("r", "A1"))
                    while len(values) <= index:
                        values.append("")
                    values[index] = _cell_value(cell, shared)
                while values and values[-1] == "":
                    values.pop()
                rows.append(values)
            sheets[sheet_name] = rows
        return [name for name, _ in sheet_paths], sheets


def extract_table(rows: list[list[str]], first_header: str) -> tuple[list[str], list[list[str]]]:
    """Find a table by its first header and return header plus contiguous populated rows."""
    header_index = next(
        (index for index, row in enumerate(rows) if row and row[0] == first_header),
        None,
    )
    if header_index is None:
        raise ValueError(f"표 머리글을 찾지 못했습니다: {first_header}")
    header = list(rows[header_index])
    while header and header[-1] == "":
        header.pop()
    data: list[list[str]] = []
    for row in rows[header_index + 1 :]:
        padded = list(row[: len(header)]) + [""] * max(0, len(header) - len(row))
        if not any(value != "" for value in padded):
            break
        data.append(padded)
    return header, data


def duplicate_values(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
