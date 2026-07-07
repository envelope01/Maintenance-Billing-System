import pandas as pd

RECURRING_CHARGE_COLUMNS = [
    "Service M Chrg.",
    "Sinking Fund",
    "Repair & Maintenance",
    "Edu.",
    "NOC Charges",
    "Parking Charges",
]

GOOGLE_FORMULA_COLUMNS = [
    "Regular Dues",
    "Current Bill Amt",
    "Total Dues",
]


def _number_series(df, column, default=0):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")

    values = df[column].astype(str).str.replace(",", "", regex=False).str.strip()

    return pd.to_numeric(values, errors="coerce").fillna(default)


def _clean_money_series(values):
    values = values.round(2)

    if values.empty or ((values % 1).abs() < 0.000001).all():
        return values.astype("int64")

    return values


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
    Prepare next month's ledger from the closing balance of the current month.

    Settlement is stored as a net balance at month end:
    positive = excess paid, zero = fully settled, negative = unpaid amount.
    """
    current_month_df = current_month_df.copy()

    # -----------------------------
    # Clean Columns & Room Numbers
    # -----------------------------
    current_month_df.columns = current_month_df.columns.str.strip()
    current_month_df["Room No"] = current_month_df["Room No"].astype(str).str.strip()

    df = current_month_df.copy()

    # -----------------------------
    # Closing balance from current month
    # -----------------------------
    settlement = _number_series(df, "Settlement")
    current_balance_advance = _number_series(df, "Balance Advance")

    unpaid_from_previous_month = (-settlement).clip(lower=0)
    available_advance = current_balance_advance + settlement.clip(lower=0)

    # -----------------------------
    # Reset month-specific fields before calculating the next month's credit use.
    # -----------------------------
    df["Other"] = 0
    df["Extra Charges"] = ""
    df["Late Chrg / Penalty"] = 0
    df["Status"] = ""
    df["Settlement"] = 0

    gross_current_bill = pd.Series(0, index=df.index, dtype="float64")
    for column in RECURRING_CHARGE_COLUMNS:
        gross_current_bill += _number_series(df, column)

    adjustment = pd.concat(
        [available_advance, gross_current_bill],
        axis=1
    ).min(axis=1)

    df["Previous dues"] = _clean_money_series(unpaid_from_previous_month)
    df["Adjustment"] = _clean_money_series(adjustment)
    df["Balance Advance"] = _clean_money_series(available_advance - adjustment)

    # -----------------------------
    # Bill Number Setup & Sorting
    # -----------------------------
    df["Bill No"] = pd.to_numeric(df["Bill No"], errors="coerce")
    last_bill = int(df["Bill No"].max())

    # Ab sorting aur reset index safe hai kyunki carry forward ho chuka hai
    df = df.sort_values("Bill No").reset_index(drop=True)
    df["Bill No"] = range(last_bill + 1, last_bill + 1 + len(df))

    # -----------------------------
    # Next Month
    # -----------------------------
    df["Month & Year"] = next_month

    # -----------------------------
    # Google Sheets owns these calculations.
    # -----------------------------
    for column in GOOGLE_FORMULA_COLUMNS:
        if column in df.columns:
            df[column] = ""

    return df
