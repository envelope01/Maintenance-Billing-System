import re

import pdfplumber
import pandas as pd
import numpy as np

MIN_PARTIAL_MATCH_LENGTH = 3
INVALID_MAPPING_VALUES = {"", "NAN", "NONE"}


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

    if len(target) >= MIN_PARTIAL_MATCH_LENGTH and target in compact_description:
        return 800 + len(target)

    best_score = None

    for candidate in description_candidates:
        if candidate == target:
            return 1000 + len(target)

        if (
            len(candidate) >= MIN_PARTIAL_MATCH_LENGTH
            and candidate in target
        ):
            best_score = max(best_score or 0, 600 + len(candidate))

    for prefix_length in range(len(target) - 1, MIN_PARTIAL_MATCH_LENGTH - 1, -1):
        if target[:prefix_length] in compact_description:
            best_score = max(best_score or 0, 700 + prefix_length)
            break

    return best_score

def extract_bank_statement(pdf_file):
    all_rows = []
    pdf_file.seek(0)
    
    # 1. Extract tables using your logic
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table_data = page.extract_table()
            if table_data:
                all_rows.extend(table_data)

    # 2. Convert to DataFrame
    if not all_rows:
        raise ValueError("No transaction table found in the uploaded statement.")
    
    df = pd.DataFrame(all_rows)

    # 3. Promote header
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)

    # 4. Filter duplicate headers
    df = df[df.iloc[:, 0] != df.columns[0]].reset_index(drop=True)
    
    # ----------------------------------------------------
    # DATA CLEANING: Strict column formatting
    # ----------------------------------------------------
    # Remove extra spaces from column names
    df.columns = df.columns.str.strip()
    
    # Keep only necessary columns (avoiding KeyErrors if extra spaces exist)
    target_cols = ['Value Date', 'Description', 'Credit']
    available_cols = [c for c in df.columns if c in target_cols]
    df = df[available_cols].copy()

    # Clean Credit column: Remove commas, convert to numeric, replace blank/nan with 0
    df['Credit'] = df['Credit'].astype(str).str.replace(',', '', regex=False)
    df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0)

    # Filter out rows where Credit is 0 (we only care about money received)
    valid_payments = df[df['Credit'] > 0].copy()
    valid_payments = valid_payments.dropna(subset=["Description","Value Date"])
    
    return valid_payments



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
