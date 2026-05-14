"""Locate accessibility failures on tagged PDF pages via structure tree (StructTreeRoot)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pikepdf

logger = logging.getLogger(__name__)

RuleLocator = Callable[[str | Path], list[int]]

RULE_LOCATORS: dict[tuple[str, str], RuleLocator] = {}

MANUAL_RULES: set[tuple[str, str]] = {
    ("Document", "Logical Reading Order"),
    ("Document", "Color contrast"),
}

_TABLE_ROW_PARENTS = frozenset({"/Table", "/THead", "/TBody", "/TFoot"})
_HEADING_TAGS = frozenset({f"/H{i}" for i in range(1, 7)})
_OTHER_ALT_STRUCTURE_TYPES = frozenset({"/Formula"})


def _normalize_detail_entry(entry: Any) -> dict[str, str]:
    if isinstance(entry, str):
        try:
            entry = json.loads(entry)
        except (json.JSONDecodeError, TypeError):
            return {"Rule": "", "Status": "", "Description": ""}
    if not isinstance(entry, dict):
        return {"Rule": "", "Status": "", "Description": ""}
    rule = entry.get("Rule") or entry.get("rule") or entry.get("Name") or entry.get("name") or ""
    status = entry.get("Status") or entry.get("status") or entry.get("Result") or entry.get("result") or ""
    desc = entry.get("Description") or entry.get("description") or entry.get("Message") or entry.get("message") or ""
    return {
        "Rule": str(rule).strip(),
        "Status": str(status).strip(),
        "Description": str(desc).strip(),
    }


def _struct_type(elem: Any) -> str:
    if not hasattr(elem, "get"):
        return ""
    s = elem.get("/S")
    if s is None:
        return ""
    t = str(s)
    if t and not t.startswith("/"):
        return "/" + t
    return t


def _has_summary(elem: Any) -> bool:
    if not hasattr(elem, "get"):
        return False
    summary = elem.get("/Summary")
    if summary is not None:
        text = str(summary).strip()
        if text:
            return True
    attrs = elem.get("/A")
    if attrs is None:
        return False
    attr_list = list(attrs) if isinstance(attrs, pikepdf.Array) else [attrs]
    for attr in attr_list:
        if isinstance(attr, pikepdf.Dictionary):
            s2 = attr.get("/Summary")
            if s2 is not None and str(s2).strip():
                return True
    return False


def _has_usable_alt(elem: Any) -> bool:
    if not hasattr(elem, "get"):
        return False
    alt = elem.get("/Alt")
    if alt is not None and str(alt).strip():
        return True
    attrs = elem.get("/A")
    if attrs is None:
        return False
    attr_list = list(attrs) if isinstance(attrs, pikepdf.Array) else [attrs]
    for attr in attr_list:
        if isinstance(attr, pikepdf.Dictionary):
            a2 = attr.get("/Alt")
            if a2 is not None and str(a2).strip():
                return True
    return False


def _iter_kids(k: Any) -> Iterator[Any]:
    if k is None:
        return
    if isinstance(k, pikepdf.Array):
        for item in k:
            yield item
    else:
        yield k


def _page_num_for_ref(pg: Any, page_lookup: dict[tuple[int, int], int]) -> int | None:
    if pg is None:
        return None
    if hasattr(pg, "objgen"):
        return page_lookup.get(pg.objgen)
    return None


def _visited_key(obj: Any) -> Any:
    if hasattr(obj, "objgen"):
        return obj.objgen
    return id(obj)


def _collect_pages_from_subtree(
    elem: Any,
    page_lookup: dict[tuple[int, int], int],
    visited: set[Any],
) -> set[int]:
    """Find page numbers from /Pg on descendants (MCR, nested rows) when the Table has no inherited /Pg."""
    found: set[int] = set()
    if not hasattr(elem, "get"):
        return found
    stack: list[Any] = list(_iter_kids(elem.get("/K")))

    while stack:
        current = stack.pop()
        if isinstance(current, pikepdf.Stream):
            continue
        if not hasattr(current, "get"):
            continue
        vk = _visited_key(current)
        if vk in visited:
            continue
        visited.add(vk)

        pg = current.get("/Pg")
        pnum = _page_num_for_ref(pg, page_lookup)
        if pnum is not None:
            found.add(pnum)

        for kid in _iter_kids(current.get("/K")):
            stack.append(kid)

    return found


def _page_of(elem: Any, inherited: int | None, page_lookup: dict[tuple[int, int], int]) -> int | None:
    if not hasattr(elem, "get"):
        return inherited
    pg = elem.get("/Pg")
    pnum = _page_num_for_ref(pg, page_lookup)
    if pnum is not None:
        return pnum
    return inherited


@contextmanager
def _open_pdf_for_scan(pdf_path: str | Path):
    """Open PDF, yield (pdf, struct_root, page_lookup). Caller must not use pdf after context exits."""
    path = Path(pdf_path)
    pdf: pikepdf.Pdf | None = None
    try:
        pdf = pikepdf.open(path)
        struct_root = pdf.Root.get("/StructTreeRoot")
        page_lookup: dict[tuple[int, int], int] = {}
        for idx, page in enumerate(pdf.pages):
            if hasattr(page, "objgen"):
                page_lookup[page.objgen] = idx + 1
        yield pdf, struct_root, page_lookup
    finally:
        if pdf is not None:
            pdf.close()


def _walk_tree(
    struct_root: Any,
    page_lookup: dict[tuple[int, int], int],
) -> Iterator[tuple[Any, int | None, str]]:
    """
    Preorder DFS over structure tree. Yields (node, current_page, parent_struct_tag).
    parent_struct_tag is the /S of the immediate parent dictionary ("" if unknown/root).
    """
    if struct_root is None:
        return

    def walk(node: Any, inherited_page: int | None, parent_tag: str) -> Iterator[tuple[Any, int | None, str]]:
        if node is None or isinstance(node, pikepdf.Stream):
            return
        if isinstance(node, (int, float, str, bool)):
            return
        if not hasattr(node, "get"):
            return
        current_page = _page_of(node, inherited_page, page_lookup)
        my_tag = _struct_type(node)
        yield (node, current_page, parent_tag)
        for kid in _iter_kids(node.get("/K")):
            yield from walk(kid, current_page, my_tag)

    yield from walk(struct_root, None, "")


def _resolve_page_for_node(node: Any, page: int | None, page_lookup: dict[tuple[int, int], int]) -> int | None:
    if page is not None:
        return page
    if hasattr(node, "get"):
        extra = _collect_pages_from_subtree(node, page_lookup, set())
        if extra:
            return min(extra)
    return None


# --- Locators -----------------------------------------------------------------


def find_tables_without_summary(pdf_path: str | Path) -> list[int]:
    """Return 1-indexed page numbers of /Table structure elements missing a usable /Summary."""
    failing_pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []

            def walk(node: Any, inherited_page: int | None = None) -> None:
                if node is None or isinstance(node, pikepdf.Stream):
                    return
                if isinstance(node, (int, float, str, bool)):
                    return
                if not hasattr(node, "get"):
                    return
                current_page = _page_of(node, inherited_page, page_lookup)
                tag = _struct_type(node)
                if tag == "/Table" and not _has_summary(node):
                    if current_page is not None:
                        failing_pages.add(current_page)
                    else:
                        extra = _collect_pages_from_subtree(node, page_lookup, set())
                        failing_pages.update(extra)
                for kid in _iter_kids(node.get("/K")):
                    walk(kid, current_page)

            walk(struct_root)
    except Exception as exc:
        logger.warning("find_tables_without_summary failed: %s", exc)
        return []
    return sorted(failing_pages)


def find_table_rows_wrong_parent(pdf_path: str | Path) -> list[int]:
    """TR must be a child of Table, THead, TBody, or TFoot."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, parent_tag in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) != "/TR":
                    continue
                if parent_tag in _TABLE_ROW_PARENTS:
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_table_rows_wrong_parent failed: %s", exc)
        return []
    return sorted(pages)


def find_table_th_td_wrong_parent(pdf_path: str | Path) -> list[int]:
    """TH and TD must be children of TR."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, parent_tag in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) not in ("/TH", "/TD"):
                    continue
                if parent_tag == "/TR":
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_table_th_td_wrong_parent failed: %s", exc)
        return []
    return sorted(pages)


def _table_subtree_has_th(table_node: Any) -> bool:
    """True if any /TH exists under table_node excluding /TH inside nested /Table subtrees."""

    def dfs(n: Any) -> bool:
        if n is None or isinstance(n, pikepdf.Stream) or not hasattr(n, "get"):
            return False
        t = _struct_type(n)
        if t == "/TH":
            return True
        if t == "/Table" and n is not table_node:
            return False
        for kid in _iter_kids(n.get("/K")):
            if dfs(kid):
                return True
        return False

    return dfs(table_node)


def find_tables_without_headers(pdf_path: str | Path) -> list[int]:
    """Tables should have headers: at least one /TH in the table subtree (excluding nested tables)."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, _parent in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) != "/Table":
                    continue
                if _table_subtree_has_th(node):
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_tables_without_headers failed: %s", exc)
        return []
    return sorted(pages)


def _tr_direct_th_td_count(tr_node: Any) -> int:
    if not hasattr(tr_node, "get"):
        return 0
    n = 0
    for kid in _iter_kids(tr_node.get("/K")):
        if not hasattr(kid, "get"):
            continue
        t = _struct_type(kid)
        if t in ("/TH", "/TD"):
            n += 1
    return n


def _collect_tr_nodes_under_table(table_node: Any) -> list[Any]:
    rows: list[Any] = []

    def dfs(n: Any) -> None:
        if n is None or isinstance(n, pikepdf.Stream) or not hasattr(n, "get"):
            return
        t = _struct_type(n)
        if t == "/Table" and n is not table_node:
            return
        if t == "/TR":
            rows.append(n)
        for kid in _iter_kids(n.get("/K")):
            dfs(kid)

    dfs(table_node)
    return rows


def find_tables_irregular(pdf_path: str | Path) -> list[int]:
    """Tables must contain the same number of columns in each row (TH+TD count per TR)."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, _parent in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) != "/Table":
                    continue
                tr_list = _collect_tr_nodes_under_table(node)
                if len(tr_list) < 2:
                    continue
                counts = [_tr_direct_th_td_count(tr) for tr in tr_list]
                counts = [c for c in counts if c > 0]
                if len(counts) < 2:
                    continue
                if len(set(counts)) > 1:
                    p = _resolve_page_for_node(node, page, page_lookup)
                    if p is not None:
                        pages.add(p)
    except Exception as exc:
        logger.warning("find_tables_irregular failed: %s", exc)
        return []
    return sorted(pages)


def find_lists_li_wrong_parent(pdf_path: str | Path) -> list[int]:
    """LI must be a child of L."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, parent_tag in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) != "/LI":
                    continue
                if parent_tag == "/L":
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_lists_li_wrong_parent failed: %s", exc)
        return []
    return sorted(pages)


def find_lists_lbl_lbody_wrong_parent(pdf_path: str | Path) -> list[int]:
    """Lbl and LBody must be children of LI."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, parent_tag in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) not in ("/Lbl", "/LBody"):
                    continue
                if parent_tag == "/LI":
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_lists_lbl_lbody_wrong_parent failed: %s", exc)
        return []
    return sorted(pages)


def find_headings_inappropriate_nesting(pdf_path: str | Path) -> list[int]:
    """Heading levels must not skip (e.g. H2 then H4). Preorder struct walk approximates reading order."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            last_level: int | None = None
            for node, page, _parent in _walk_tree(struct_root, page_lookup):
                tag = _struct_type(node)
                if tag not in _HEADING_TAGS:
                    continue
                level = int(tag[2:])  # "/H1" -> 1
                if last_level is not None and level > last_level + 1:
                    p = _resolve_page_for_node(node, page, page_lookup)
                    if p is not None:
                        pages.add(p)
                last_level = level
    except Exception as exc:
        logger.warning("find_headings_inappropriate_nesting failed: %s", exc)
        return []
    return sorted(pages)


def find_figures_without_alt(pdf_path: str | Path) -> list[int]:
    """Figures require alternate text."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, _parent in _walk_tree(struct_root, page_lookup):
                if _struct_type(node) != "/Figure":
                    continue
                if _has_usable_alt(node):
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_figures_without_alt failed: %s", exc)
        return []
    return sorted(pages)


def find_other_elements_without_alt(pdf_path: str | Path) -> list[int]:
    """Other elements that require alternate text (e.g. Formula)."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []
            for node, page, _parent in _walk_tree(struct_root, page_lookup):
                tag = _struct_type(node)
                if tag not in _OTHER_ALT_STRUCTURE_TYPES:
                    continue
                if _has_usable_alt(node):
                    continue
                p = _resolve_page_for_node(node, page, page_lookup)
                if p is not None:
                    pages.add(p)
    except Exception as exc:
        logger.warning("find_other_elements_without_alt failed: %s", exc)
        return []
    return sorted(pages)


def find_nested_alt_text(pdf_path: str | Path) -> list[int]:
    """Alternate text nested so inner text may never be read (ancestor and descendant both have Alt)."""
    pages: set[int] = set()
    try:
        with _open_pdf_for_scan(pdf_path) as (_pdf, struct_root, page_lookup):
            if struct_root is None:
                return []

            def walk(node: Any, inherited_page: int | None, ancestor_has_alt: bool) -> None:
                if node is None or isinstance(node, pikepdf.Stream):
                    return
                if isinstance(node, (int, float, str, bool)):
                    return
                if not hasattr(node, "get"):
                    return
                current_page = _page_of(node, inherited_page, page_lookup)
                has_alt = _has_usable_alt(node)
                if has_alt and ancestor_has_alt:
                    p = _resolve_page_for_node(node, current_page, page_lookup)
                    if p is not None:
                        pages.add(p)
                next_ancestor = ancestor_has_alt or has_alt
                for kid in _iter_kids(node.get("/K")):
                    walk(kid, current_page, next_ancestor)

            walk(struct_root, None, False)
    except Exception as exc:
        logger.warning("find_nested_alt_text failed: %s", exc)
        return []
    return sorted(pages)


# Register all locators (do not split — keys must match Adobe JSON exactly)
RULE_LOCATORS[("Tables", "Summary")] = find_tables_without_summary
RULE_LOCATORS[("Tables", "Rows")] = find_table_rows_wrong_parent
RULE_LOCATORS[("Tables", "TH and TD")] = find_table_th_td_wrong_parent
RULE_LOCATORS[("Tables", "Headers")] = find_tables_without_headers
RULE_LOCATORS[("Tables", "Regularity")] = find_tables_irregular
RULE_LOCATORS[("Lists", "List items")] = find_lists_li_wrong_parent
RULE_LOCATORS[("Lists", "Lbl and LBody")] = find_lists_lbl_lbody_wrong_parent
RULE_LOCATORS[("Headings", "Appropriate nesting")] = find_headings_inappropriate_nesting
RULE_LOCATORS[("Alternate Text", "Figures alternate text")] = find_figures_without_alt
RULE_LOCATORS[("Alternate Text", "Other elements alternate text")] = find_other_elements_without_alt
RULE_LOCATORS[("Alternate Text", "Nested alternate text")] = find_nested_alt_text


def _unlocatable_row(cat_str: str, rule_name: str, status_raw: str, description: str) -> dict[str, Any]:
    return {
        "category": cat_str,
        "rule": rule_name,
        "status": status_raw,
        "description": description,
    }


def enrich_report(report: dict[str, Any], pdf_path: str | Path) -> dict[str, Any]:
    """
    Merge Adobe accessibility JSON with per-page localization from the tagged PDF.

    Returns keys: summary, failures_by_page, unlocatable_failures, manual_check_required.
    """
    summary = report.get("Summary") if isinstance(report.get("Summary"), dict) else {}
    detailed = report.get("Detailed Report")
    if not isinstance(detailed, dict):
        detailed = {}

    per_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unlocatable: list[dict[str, Any]] = []
    manual_check_required: list[dict[str, Any]] = []

    pdf_path = Path(pdf_path)

    for category, rules in detailed.items():
        if not isinstance(rules, list):
            continue
        cat_str = str(category).strip()
        for raw in rules:
            norm = _normalize_detail_entry(raw)
            rule_name = norm["Rule"]
            status_raw = norm["Status"]
            status_lower = status_raw.lower()

            if "needs manual check" in status_lower:
                row: dict[str, Any] = {
                    "category": cat_str,
                    "rule": rule_name,
                    "status": status_raw,
                    "description": norm["Description"],
                    "scope": "document",
                    "review_hint": "Review full document",
                }
                if (cat_str, rule_name) in MANUAL_RULES:
                    row["manual_rule_class"] = "known_document_level"
                manual_check_required.append(row)
                continue

            if "failed" not in status_lower:
                continue

            key = (cat_str, rule_name)
            locator = RULE_LOCATORS.get(key)
            if locator is None:
                unlocatable.append(_unlocatable_row(cat_str, rule_name, status_raw, norm["Description"]))
                continue

            try:
                pages = locator(pdf_path)
            except Exception as exc:
                logger.warning("Locator failed for %s: %s", key, exc)
                pages = []

            if not pages:
                unlocatable.append(_unlocatable_row(cat_str, rule_name, status_raw, norm["Description"]))
                continue

            entry = {
                "category": cat_str,
                "rule": rule_name,
                "status": status_raw,
                "description": norm["Description"],
            }
            for page in pages:
                per_page[int(page)].append(entry.copy())

    failures_by_page = {str(k): v for k, v in sorted(per_page.items())}

    return {
        "summary": summary,
        "failures_by_page": failures_by_page,
        "unlocatable_failures": unlocatable,
        "manual_check_required": manual_check_required,
    }
