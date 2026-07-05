import pandas as pd

def get_next_month(statement_month):
    current = pd.to_datetime(statement_month,dayfirst=True)
    next_month = current + pd.DateOffset(months=1)
    return next_month.strftime("%d-%m-%Y")


def validate_initialization(current_month_df, ledger_df, next_month):
    """
    Validate whether next month
    can be initialized.
    """

    current_month_df = current_month_df.copy()
    ledger_df = ledger_df.copy()

    current_month_df.columns = (current_month_df.columns.str.strip())
    ledger_df.columns = (ledger_df.columns.str.strip())

    current_month_exists = bool(not current_month_df.empty)

    if current_month_exists:
        blank_status = (current_month_df["Status"].fillna("").astype(str).str.strip().eq("").sum())
    else:
        blank_status = 0

    # -----------------------------
    # Check Next Month Exists
    # -----------------------------
    month_exists = bool(ledger_df["Month & Year"].eq(next_month).any())

    # -----------------------------
    # Validation Result
    # -----------------------------
    return {
        "valid": (current_month_exists and blank_status == 0 and not month_exists),
        "current_month_exists": current_month_exists,
        "blank_status": int(blank_status),
        "month_exists": month_exists
    }

def prepare_new_month_dataframe(current_month_df, next_month):
    """
    Prepare next month's ledger using only Settlement
    to populate carry-forward values, and calculate dues for preview.
    """
    current_month_df = current_month_df.copy()

    # -----------------------------
    # Clean Columns & Room Numbers
    # -----------------------------
    current_month_df.columns = current_month_df.columns.str.strip()
    current_month_df["Room No"] = current_month_df["Room No"].astype(str).str.strip()

    df = current_month_df.copy()

    # -----------------------------
    # 1. Carry Forward (FIXED LOGIC)
    # Isko sort karne se PEHLE run karna zaroori hai!
    # -----------------------------
    settlement = pd.to_numeric(df["Settlement"], errors="coerce").fillna(0)
    df["Previous dues"] = settlement.where(settlement < 0, 0).abs()
    df["Adjustment"] = settlement.where(settlement > 0, 0)

    # -----------------------------
    # Next Month
    # -----------------------------
    df["Month & Year"] = next_month

    # -----------------------------
    # Bill Number Setup & Sorting
    # -----------------------------
    df["Bill No"] = pd.to_numeric(df["Bill No"], errors="coerce")
    last_bill = int(df["Bill No"].max())

    # Ab sorting aur reset index safe hai kyunki carry forward ho chuka hai
    df = df.sort_values("Bill No").reset_index(drop=True)
    df["Bill No"] = range(last_bill + 1, last_bill + 1 + len(df))

    # -----------------------------
    # Reset Monthly Fields
    # -----------------------------
    df["Other"] = 0
    df["Extra Charges"] = ""
    df["Late Chrg / Penalty"] = 0
    df["Status"] = ""
    df["Settlement"] = 0  # Ab isko 0 kar sakte hain

    # -----------------------------
    # Calculations for Preview
    # -----------------------------
    df["Service M Chrg."] = pd.to_numeric(df.get("Service M Chrg.", 0), errors="coerce").fillna(0)
    df["Sinking Fund"] = pd.to_numeric(df.get("Sinking Fund", 0), errors="coerce").fillna(0)
    df["Repair & Maintenance"] = pd.to_numeric(df.get("Repair & Maintenance", 0), errors="coerce").fillna(0)
    df["Edu."] = pd.to_numeric(df.get("Edu.", 0), errors="coerce").fillna(0)
    df["NOC Charges"] = pd.to_numeric(df.get("NOC Charges", 0), errors="coerce").fillna(0)
    df["Parking Charges"] = pd.to_numeric(df.get("Parking Charges", 0), errors="coerce").fillna(0)
    
    df["Regular Dues"] = (
        df["Service M Chrg."]
        + df["Sinking Fund"]
        + df["Repair & Maintenance"]
        + df["Edu."]
        + df["NOC Charges"]
        + df["Parking Charges"]
    )

    df["Total Dues"] = (
        df["Regular Dues"]
        + df["Previous dues"]
        + df["Late Chrg / Penalty"]
        - df["Adjustment"]
    )

    df["Current Bill Amt"] = (
        df["Regular Dues"]
        + df["Other"]
    )

    df["Balance Advance"] = 0

    return df