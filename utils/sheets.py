import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd


def append_to_ledger(new_month_df):

    conn = st.connection("gsheets",type=GSheetsConnection)

    ledger_df = conn.read(worksheet="testData",ttl=0)

    updated_df = pd.concat([ledger_df, new_month_df],ignore_index=True)

    conn.update(worksheet="testData",data=updated_df)

    return True



def update_status_to_sheet(report_df,statement_month):
    """
    Update only Status column in Google Sheet
    for the selected billing month.
    """

    conn = st.connection("gsheets",type=GSheetsConnection)

    ledger_df = conn.read(worksheet="testData",ttl=0)

    ledger_df.columns = (ledger_df.columns.str.strip())

    report_df = report_df.copy()
    report_df.columns = (report_df.columns.str.strip())

    ledger_df["Room No"] = (ledger_df["Room No"].astype(str).str.strip())

    report_df["Room No"] = (report_df["Room No"].astype(str).str.strip())

    status_mapping = {
        "Paid": "Paid Online",
        "Partially Paid": "Partially Paid",
        "Unpaid": "Unpaid"
    }

    report_df["Status"] = (report_df["Status"].map(status_mapping))

    status_lookup = dict(
        zip(
            report_df["Room No"],
            report_df["Status"]
        )
    )

    mask = (ledger_df["Month & Year"]== statement_month)

    ledger_df.loc[mask,"Status"] = (ledger_df.loc[mask,"Room No"].map(status_lookup).fillna(ledger_df.loc[mask,"Status"]))

    conn.update(worksheet="testData",data=ledger_df)

    return True