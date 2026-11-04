from app.ingestion.parsing.base import render_table


def test_header_row_becomes_column_names_on_every_row():
    rows = [["Plan", "Price"], ["Free", "$0"], ["Pro", "$12"]]

    assert render_table(rows) == "Plan: Free | Price: $0\nPlan: Pro | Price: $12"


def test_empty_cells_are_skipped():
    rows = [["Plan", "Price", "Notes"], ["Free", "$0", ""], ["Pro", None, "Popular"]]

    assert render_table(rows) == "Plan: Free | Price: $0\nPlan: Pro | Notes: Popular"


def test_numeric_first_row_is_not_a_header():
    rows = [["2024", "120"], ["2025", "300"]]

    assert render_table(rows) == "2024 | 120\n2025 | 300"


def test_single_row_has_no_header():
    assert render_table([["Only", "row"]]) == "Only | row"


def test_cell_text_is_normalized_and_empty_rows_dropped():
    rows = [["Plan", "Price"], ["", ""], ["Pro\nannual", "  $12 "]]

    assert render_table(rows) == "Plan: Pro annual | Price: $12"


def test_empty_table_renders_nothing():
    assert render_table([["", ""], [None, None]]) == ""
