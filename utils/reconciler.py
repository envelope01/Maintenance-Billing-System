import re
from difflib import SequenceMatcher

import pdfplumber
import pandas as pd
import numpy as np

INVALID_MAPPING_VALUES = {"", "NAN", "NONE"}
BANK_DATE_PATTERN = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")
ROW_START_DATE_PATTERN = re.compile(r"^\s*\d{2}-[A-Za-z]{3}-\d{4}\b")
AMOUNT_PATTERN = re.compile(
    r"(?<![A-Z0-9])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Z0-9])-?\d+\.\d+"
)
CREDIT_KEYWORDS = (
    "/CR/",
    "IMPSNPC",
    "CREDIT",
)
STATEMENT_TOTAL_PATTERN = re.compile(
    r"Total\s+Debits\s*\(\d+\)\s+and\s+Credits\s*\(\d+\)\s*:\s*"
    r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s+"
    r"(?P<credit>\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
    re.IGNORECASE,
)


def _normalize_identifier(value):
    """
    Normalize bank identifiers for matching.

    Spaces, punctuation, and casing are ignored because bank descriptions often
    add separators or remove spaces from names.
    """
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _split_mapping_ids(bank_mapping_id):
    raw_value = str(bank_mapping_id).strip()

    if raw_value.upper() in INVALID_MAPPING_VALUES or "#N/A" in raw_value.upper():
        return []

    mapping_ids = []

    for value in raw_value.split(","):
        value = value.strip()
        normalized_value = _normalize_identifier(value)

        if (
            value.upper() in INVALID_MAPPING_VALUES
            or "#N/A" in value.upper()
            or not normalized_value
        ):
            continue

        mapping_ids.append(
            {
                "raw": value,
                "normalized": normalized_value,
            }
        )

    return mapping_ids


def _description_candidates(description):
    text = str(description).upper().replace("\n", " ").replace("\r", " ")
    tokens = [
        _normalize_identifier(token)
        for token in re.split(r"[^A-Z0-9]+", text)
    ]

    candidates = {
        token
        for token in tokens
        if token
    }

    compact_description = _normalize_identifier(text)
    if compact_description:
        candidates.add(compact_description)

    return compact_description, candidates


def _get_match_score(mapping_id, compact_description, description_candidates):
    target = mapping_id["normalized"]

    if not target or not compact_description:
        return None

    if target in description_candidates:
        return 1000 + len(target)

    if target in compact_description:
        return 1000 + len(target)

    return None


def _clean_amount(value):
    value = str(value).replace(",", "").strip()
    return pd.to_numeric(value, errors="coerce")


def _find_column(columns, required_words, optional_words=None):
    optional_words = optional_words or []

    for column in columns:
        normalized_column = str(column).strip().lower()

        if all(word in normalized_column for word in required_words):
            return column

    for column in columns:
        normalized_column = str(column).strip().lower()

        if any(word in normalized_column for word in optional_words):
            return column

    return None


def _table_rows_to_dataframe(all_rows):
    if not all_rows:
        return pd.DataFrame(columns=["Value Date", "Description", "Credit", "Reference No"])

    df = pd.DataFrame(all_rows)
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    df.columns = df.columns.map(lambda value: str(value).strip())

    first_column = df.columns[0]
    df = df[df.iloc[:, 0].astype(str).str.strip() != str(first_column).strip()].reset_index(drop=True)

    value_date_col = _find_column(df.columns, ["value", "date"])
    description_col = _find_column(df.columns, ["description"], optional_words=["particular", "narration"])
    credit_col = _find_column(df.columns, ["credit"])
    reference_col = _find_column(df.columns, ["ref"], optional_words=["cheque", "utr"])

    if description_col is None or credit_col is None:
        return pd.DataFrame(columns=["Value Date", "Description", "Credit", "Reference No"])

    result = pd.DataFrame()
    result["Value Date"] = df[value_date_col] if value_date_col is not None else ""
    result["Description"] = df[description_col]
    result["Credit"] = df[credit_col]
    result["Reference No"] = df[reference_col] if reference_col is not None else ""

    return result


def _looks_like_credit_transaction(text):
    normalized_text = f" {str(text).upper()} "

    return any(keyword in normalized_text for keyword in CREDIT_KEYWORDS)


def _extract_reference_no(text):
    match = re.search(r"\b\d{10,18}\b", str(text))

    if not match:
        return ""

    return match.group(0)


def _parse_text_transaction_block(block_lines):
    text = " ".join(str(line).strip() for line in block_lines if str(line).strip())
    upper_text = text.upper()

    if "TOTAL DEBITS" in upper_text or "OPENING BALANCE" in upper_text:
        return None

    if not _looks_like_credit_transaction(text):
        return None

    dates = BANK_DATE_PATTERN.findall(text)
    amounts = AMOUNT_PATTERN.findall(text)

    if not dates or len(amounts) < 2:
        return None

    return {
        "Value Date": dates[1] if len(dates) > 1 else dates[0],
        "Description": re.sub(ROW_START_DATE_PATTERN, "", text).strip(),
        "Credit": amounts[-2],
        "Reference No": _extract_reference_no(text),
    }


def _extract_text_credit_rows(pdf):
    rows = []

    for page in pdf.pages:
        text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        current_block = []

        for line in lines:
            if ROW_START_DATE_PATTERN.match(line):
                if current_block:
                    row = _parse_text_transaction_block(current_block)
                    if row is not None:
                        rows.append(row)

                current_block = [line]
            elif current_block:
                current_block.append(line)

        if current_block:
            row = _parse_text_transaction_block(current_block)
            if row is not None:
                rows.append(row)

    return pd.DataFrame(rows, columns=["Value Date", "Description", "Credit", "Reference No"])


def _extract_statement_credit_total(pdf):
    for page in pdf.pages:
        text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
        match = STATEMENT_TOTAL_PATTERN.search(text)

        if match:
            return _clean_amount(match.group("credit"))

    return None


def _same_payment(row, selected_row):
    if (
        row["Value Date"] != selected_row["Value Date"]
        or row["_credit_key"] != selected_row["_credit_key"]
    ):
        return False

    if row["Reference No"] and row["Reference No"] == selected_row["Reference No"]:
        return True

    row_desc = row["_desc_key"]
    selected_desc = selected_row["_desc_key"]

    if not row_desc or not selected_desc:
        return False

    if row_desc in selected_desc or selected_desc in row_desc:
        return True

    return SequenceMatcher(None, row_desc, selected_desc).ratio() >= 0.90


def _dedupe_payments(df):
    df = df.copy()
    if "_source" not in df.columns:
        df["_source"] = "table"

    df["Reference No"] = df["Reference No"].fillna("").astype(str).str.strip()
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    df["Value Date"] = df["Value Date"].fillna("").astype(str).str.strip()
    df["_source"] = df["_source"].fillna("table").astype(str)
    df["Credit"] = df["Credit"].apply(_clean_amount).fillna(0)

    df = df[df["Credit"] > 0].copy()
    df = df[
        df["Description"].ne("")
        & df["Value Date"].str.fullmatch(BANK_DATE_PATTERN)
    ].copy()

    df["_desc_key"] = df["Description"].apply(_normalize_identifier)
    df["_credit_key"] = df["Credit"].round(2)

    source_priority = {
        "table": 0,
        "text": 1,
    }
    df["_source_priority"] = df["_source"].map(source_priority).fillna(1)
    df = df.sort_values(["_source_priority"]).reset_index(drop=True)

    selected_rows = []

    for _, row in df.iterrows():
        if any(_same_payment(row, selected_row) for selected_row in selected_rows):
            continue

        selected_rows.append(row)

    if not selected_rows:
        return pd.DataFrame(columns=["Value Date", "Description", "Credit", "Reference No"])

    result = pd.DataFrame(selected_rows)
    result = result.drop(columns=["_desc_key", "_credit_key", "_source_priority", "_source"])

    return result.reset_index(drop=True)

def extract_bank_statement(pdf_file):
    all_rows = []
    pdf_file.seek(0)
    
    # 1. Extract tables and add a text fallback for rows missed at page breaks.
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table_data = page.extract_table()
            if table_data:
                all_rows.extend(table_data)

        table_df = _table_rows_to_dataframe(all_rows)
        text_df = _extract_text_credit_rows(pdf)
        statement_credit_total = _extract_statement_credit_total(pdf)

    table_df["_source"] = "table"
    text_df["_source"] = "text"
    df = pd.concat([table_df, text_df], ignore_index=True)

    if df.empty:
        raise ValueError("No transaction table found in the uploaded statement.")

    valid_payments = _dedupe_payments(df)
    result = valid_payments[["Value Date", "Description", "Credit", "Reference No"]].copy()

    if statement_credit_total is not None and not pd.isna(statement_credit_total):
        result.attrs["statement_credit_total"] = float(statement_credit_total)

    return result



def map_bank_to_rooms(raw_bank_df, master_df):

    # -----------------------------
    # Clean Master Data
    # -----------------------------
    master_df = master_df.copy()

    master_df.columns = master_df.columns.str.strip()

    master_df["Room No"] = (master_df["Room No"].astype(str).str.strip())

    # -----------------------------
    # Create Mapping Entries
    # -----------------------------
    mapping_entries = []

    for _, row in master_df.iterrows():

        for mapping_id in _split_mapping_ids(row.get("Bank_Mapping_ID", "")):
            mapping_entries.append(
                {
                    "room": row["Room No"],
                    **mapping_id,
                }
            )


    # -----------------------------
    # Find Room from Description
    # -----------------------------
    def find_room(description):

        compact_description, candidates = _description_candidates(description)
        matches = []

        for mapping_id in mapping_entries:
            score = _get_match_score(mapping_id, compact_description, candidates)

            if score is not None:
                matches.append(
                    {
                        "score": score,
                        "room": mapping_id["room"],
                    }
                )

        if not matches:
            return np.nan

        best_score = max(match["score"] for match in matches)
        best_rooms = {
            match["room"]
            for match in matches
            if match["score"] == best_score
        }

        if len(best_rooms) == 1:
            return next(iter(best_rooms))

        return np.nan

    raw_bank_df = raw_bank_df.copy()

    raw_bank_df["Mapped_Room_No"] = (raw_bank_df["Description"].apply(find_room))

    mapped_df = raw_bank_df.dropna(subset=["Mapped_Room_No"]).copy()

    unmapped_df = raw_bank_df[raw_bank_df["Mapped_Room_No"].isna()].copy()

    grouped_payments = (mapped_df.groupby("Mapped_Room_No")["Credit"].sum().reset_index())

    grouped_payments.rename(
        columns={
        "Mapped_Room_No": "Room No",
        "Credit": "Total_Paid"
        },
        inplace=True
    )

    return grouped_payments, unmapped_df


def generate_reconciliation_report(grouped_payments, master_df, ledger_df):

    # -----------------------------
    # Clean Data
    # -----------------------------
    master_df = master_df.copy()
    ledger_df = ledger_df.copy()
    grouped_payments = grouped_payments.copy()

    master_df.columns = master_df.columns.str.strip()
    ledger_df.columns = ledger_df.columns.str.strip()

    master_df["Room No"] = (master_df["Room No"].astype(str).str.strip())

    ledger_df["Room No"] = (ledger_df["Room No"].astype(str).str.strip())

    grouped_payments["Room No"] = (grouped_payments["Room No"].astype(str).str.strip())

    # -----------------------------
    # Create Base Report
    # -----------------------------
    report_df = pd.merge(
        master_df[["Room No", "Name"]],
        ledger_df[["Room No", "Total Dues"]],
        on="Room No",
        how="inner"
    )

    # -----------------------------
    # Merge Payments
    # -----------------------------
    report_df = pd.merge(report_df, grouped_payments, on="Room No", how="left")

    report_df.rename(columns={"Total_Paid": "Total Paid"}, inplace=True)

    report_df["Total Paid"] = (
        pd.to_numeric(report_df["Total Paid"], errors="coerce").fillna(0)
    )

    report_df["Total Dues"] = (
        pd.to_numeric(report_df["Total Dues"], errors="coerce").fillna(0)
    )

    # -----------------------------
    # Settlement
    # -----------------------------
    report_df["Settlement"] = report_df["Total Paid"] - report_df["Total Dues"]

    # -----------------------------
    # Status
    # -----------------------------
    def get_status(row):

        if row["Total Paid"] >= row["Total Dues"]:
            return "Paid"

        elif row["Total Paid"] > 0:
            return "Partially Paid"

        return "Unpaid"

    report_df["Status"] = report_df.apply(get_status, axis=1)

    return report_df[
        [
            "Room No",
            "Name",
            "Total Dues",
            "Total Paid",
            "Settlement",
            "Status"
        ]
    ]
