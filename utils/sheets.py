from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import pandas as pd 


def get_gspread_client():
    creds_dict = dict(st.secrets["connections"]["gsheets"])

    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

    return gspread.authorize(creds)


def append_to_ledger(new_month_df):

    gc = get_gspread_client()

    spreadsheet = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
    worksheet = spreadsheet.worksheet("testData")

    sheet_df = new_month_df.copy()

    formula_columns = [
        "Regular Dues",
        "Current Bill Amt",
        "Total Dues"
    ]

    for column in formula_columns:
        if column in sheet_df.columns:
            sheet_df[column] = ""

    values = (sheet_df.fillna("").astype(object).values.tolist())
    worksheet.append_rows(values,value_input_option="USER_ENTERED")

    return True


def update_status_to_sheet(report_df, statement_month):

    gc = get_gspread_client()

    spreadsheet = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])

    worksheet = spreadsheet.worksheet("testData")

    data = worksheet.get_all_values()

    headers = [h.strip() for h in data[0]]

    room_col = headers.index("Room No") + 1
    month_col = headers.index("Month & Year") + 1
    status_col = headers.index("Status") + 1
    settlement_col = headers.index("Settlement") + 1

    report_df = report_df.copy()

    report_df["Room No"] = (report_df["Room No"].astype(str).str.strip())

    statement_month = str(statement_month).strip()

    status_mapping = {
        "Paid": "Paid Online",
        "Partially Paid": "Partially Paid",
        "Unpaid": "Unpaid",
    }

    report_df["Sheet Status"] = (report_df["Status"].map(status_mapping))

    report_df["Settlement"] = (pd.to_numeric(report_df["Settlement"],errors="coerce").fillna(0).astype(float))

    lookup = report_df.set_index("Room No")

    updates = []

    for row_number, row in enumerate(data[1:], start=2):

        room = row[room_col - 1].strip()
        month = row[month_col - 1].strip()

        if month == statement_month and room in lookup.index:

            status_val = lookup.loc[room, "Sheet Status"]
            settlement_val = lookup.loc[room, "Settlement"]

            if isinstance(status_val, pd.Series):
                status_val = status_val.iloc[0]

            if isinstance(settlement_val, pd.Series):
                settlement_val = settlement_val.iloc[0]

            updates.append(
                {
                    "range": gspread.utils.rowcol_to_a1(
                        row_number,
                        status_col
                    ),
                    "values": [[status_val]]
                }
            )

            updates.append(
                {
                    "range": gspread.utils.rowcol_to_a1(
                        row_number,
                        settlement_col
                    ),
                    "values": [[float(settlement_val)]]
                }
            )

    if updates:
        worksheet.batch_update(updates,value_input_option="USER_ENTERED")
        
    return True
