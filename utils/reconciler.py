import pdfplumber
import pandas as pd
import numpy as np

def extract_bank_statement(pdf_file):
    all_rows = []
    
    # 1. Extract tables using your logic
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table_data = page.extract_table()
            if table_data:
                all_rows.extend(table_data)

    # 2. Convert to DataFrame
    if not all_rows:
        raise ValueError(
            "No transaction table found in the uploaded statement."
        )
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
    
    return valid_payments



def map_bank_to_rooms(raw_bank_df, master_df):

    # -----------------------------
    # Clean Master Data
    # -----------------------------
    master_df = master_df.copy()

    master_df.columns = master_df.columns.str.strip()

    master_df["Bank_Mapping_ID"] = (
        master_df["Bank_Mapping_ID"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    master_df["Room No"] = (
        master_df["Room No"]
        .astype(str)
        .str.strip()
    )

    # -----------------------------
    # Create Mapping Dictionary
    # -----------------------------
    mapping_dict = {}

    for _, row in master_df.iterrows():

        bank_id = row["Bank_Mapping_ID"]

        if (
            bank_id in ["", "NAN", "NONE"]
            or "#N/A" in bank_id
        ):
            continue

        mapping_dict[bank_id] = row["Room No"]


    # -----------------------------
    # Find Room from Description
    # -----------------------------
    def find_room(description):

        desc = (
            str(description)
            .upper()
            .replace("\n", " ")
            .replace("\r", " ")
        )

        desc = " ".join(desc.split())

        for bank_id, room in mapping_dict.items():

            if bank_id in desc:
                return room

        return np.nan

    raw_bank_df = raw_bank_df.copy()

    raw_bank_df["Mapped_Room_No"] = (
        raw_bank_df["Description"]
        .apply(find_room)
    )

    mapped_df = raw_bank_df.dropna(
        subset=["Mapped_Room_No"]
    ).copy()

    unmapped_df = raw_bank_df[
        raw_bank_df["Mapped_Room_No"].isna()
    ].copy()

    grouped_payments = (
        mapped_df
        .groupby("Mapped_Room_No")["Credit"]
        .sum()
        .reset_index()
    )

    grouped_payments.rename(
        columns={
            "Mapped_Room_No": "Room No",
            "Credit": "Total_Paid"
        },
        inplace=True
    )

    return grouped_payments, unmapped_df


def generate_reconciliation_report(
    grouped_payments,
    master_df,
    ledger_df
):

    # -----------------------------
    # Clean Data
    # -----------------------------
    master_df = master_df.copy()
    ledger_df = ledger_df.copy()
    grouped_payments = grouped_payments.copy()

    master_df.columns = master_df.columns.str.strip()
    ledger_df.columns = ledger_df.columns.str.strip()

    master_df["Room No"] = (
        master_df["Room No"]
        .astype(str)
        .str.strip()
    )

    ledger_df["Room No"] = (
        ledger_df["Room No"]
        .astype(str)
        .str.strip()
    )

    grouped_payments["Room No"] = (
        grouped_payments["Room No"]
        .astype(str)
        .str.strip()
    )

    # -----------------------------
    # Create Base Report
    # -----------------------------
    report_df = pd.merge(

        master_df[
            ["Room No", "Name"]
        ],

        ledger_df[
            ["Room No", "Total Dues"]
        ],

        on="Room No",
        how="inner"

    )

    # -----------------------------
    # Merge Payments
    # -----------------------------
    report_df = pd.merge(

        report_df,

        grouped_payments,

        on="Room No",

        how="left"

    )

    report_df["Total_Paid"] = (
        pd.to_numeric(
            report_df["Total_Paid"],
            errors="coerce"
        )
        .fillna(0)
    )

    report_df["Total Dues"] = (
        pd.to_numeric(
            report_df["Total Dues"],
            errors="coerce"
        )
        .fillna(0)
    )

    # -----------------------------
    # Difference
    # -----------------------------
    report_df["Difference"] = (
        report_df["Total Dues"]
        - report_df["Total_Paid"]
    )

    # -----------------------------
    # Status
    # -----------------------------
    def get_status(row):

        if row["Total_Paid"] >= row["Total Dues"]:

            return "Paid"

        elif row["Total_Paid"] > 0:

            return "Partially Paid"

        return "Unpaid"

    report_df["Status"] = report_df.apply(
        get_status,
        axis=1
    )

    return report_df