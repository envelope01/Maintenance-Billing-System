import pandas as pd

def get_next_month(statement_month):
    current = pd.to_datetime(
        statement_month,
        dayfirst=True
    )
    next_month = current + pd.DateOffset(months=1)
    return next_month.strftime("%d-%m-%Y")


def validate_initialization(current_month_df,ledger_df,next_month):
    """
    Validate whether next month
    can be initialized.
    """

    current_month_df = current_month_df.copy()
    ledger_df = ledger_df.copy()

    current_month_df.columns = (current_month_df.columns.str.strip())

    ledger_df.columns = (ledger_df.columns.str.strip())

    # -----------------------------
    # Check Blank Status
    # -----------------------------
    blank_status = (current_month_df["Status"].fillna("").astype(str).str.strip().eq("").sum())

    # -----------------------------
    # Check Next Month Exists
    # -----------------------------
    month_exists = (ledger_df["Month & Year"].eq(next_month).any())

    # -----------------------------
    # Validation Result
    # -----------------------------
    return {

        "valid": (blank_status == 0 and not month_exists),
        "blank_status": int(blank_status),
        "month_exists": month_exists

    }

def prepare_new_month_dataframe(current_month_df, next_month):
    """
    Prepare next month's ledger using
    reconciliation report and master data.
    """
    current_month_df = current_month_df.copy()

    # -----------------------------
    # Clean Columns
    # -----------------------------
    current_month_df.columns = (current_month_df.columns.str.strip())

    # -----------------------------
    # Clean Room Numbers
    # -----------------------------
    current_month_df["Room No"] = (current_month_df["Room No"].astype(str).str.strip())

    df = current_month_df.copy()


    # -----------------------------
    # Next Month
    # -----------------------------
    df["Month & Year"] = next_month

    # -----------------------------
    # Bill Number
    # -----------------------------
    current_month_df["Bill No"] = pd.to_numeric(current_month_df["Bill No"],errors="coerce")

    last_bill = int(current_month_df["Bill No"].max())

    df = (df.sort_values("Bill No").reset_index(drop=True))

    df["Bill No"] = range(last_bill + 1,last_bill + 1 + len(df))

    # -----------------------------
    # Reset Monthly Fields
    # -----------------------------
    df["Other"] = 0
    df["Extra Charges"] = ""
    df["Late Chrg / Penalty"] = 0
    df["Status"] = ""

    # -----------------------------
    # Regular Dues
    # -----------------------------
    df["Regular Dues"] = (
        df["Service M Chrg."]
        + df["Sinking Fund"]
        + df["Repair & Maintenance"]
        + df["Edu."]
        + df["Other"]
        + df["NOC Charges"]
        + df["Parking Charges"]
    )

    # -----------------------------
    # Keep Final Columns
    # -----------------------------
    df = df[
        [
            "Month & Year",
            "Room No",
            "Bill No",
            "Service M Chrg.",
            "Sinking Fund",
            "Repair & Maintenance",
            "Edu.",
            "NOC Charges",
            "Parking Charges",
            "Other",
            "Extra Charges",
            "Regular Dues",
            "Previous dues",
            "Late Chrg / Penalty",
            "Adjustment",
            "Total Dues",
            "Balance Advance",
            "Current Bill Amt",
            "Status",
            "Recd Advance"
        ]
    ]

    return df

