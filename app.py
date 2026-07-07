import base64
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from utils.generator import generate_monthly_bills
from utils.helpers import get_statement_month
from utils.initializer import get_next_month, prepare_new_month_dataframe, validate_initialization
from utils.reconciler import (
    extract_bank_statement,
    generate_reconciliation_report,
    map_bank_to_rooms,
)
from utils.sheets import (
    append_to_ledger,
    update_status_to_sheet
)

# --------------------------------------------------
# Page Configuration
# --------------------------------------------------
# CHANGED: layout="wide" to give columns space to breathe
st.set_page_config(
    page_title="Maintenance Billing System",
    page_icon="🏢",
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --------------------------------------------------
# Load Styles
# --------------------------------------------------
try:
    with open("assets/style.css") as css:
        st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# --------------------------------------------------
# Session State
# --------------------------------------------------
DEFAULT_STATE = {
    "report_df": None,
    "raw_bank_df": None,
    "grouped_payments": None,
    "unmapped_df": None,
    "statement_month": None,
    "reconciliation_done": False,
    "new_month_df": None,
    "status_updated": False,
    "validation": None,
    "current_month_df": None,
    "next_month": None,
}

for key, value in DEFAULT_STATE.items():
    st.session_state.setdefault(key, value)

# --------------------------------------------------
# Google Sheets Connection
# --------------------------------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    master_df = conn.read(worksheet="Master_Flats", ttl=0)
    ledger_df = conn.read(worksheet="testData", ttl=0)
except Exception as e:
    st.error(f"Google Sheets Connection Failed\n\n{e}")
    st.stop()

# --------------------------------------------------
# Sidebar Navigation (Replaces Tabs)
# --------------------------------------------------
try:
    logo_base64 = base64.b64encode(Path("assets/ibldg icon.png").read_bytes()).decode("utf-8")
    st.sidebar.markdown(
        f"""
        <div class="sidebar-logo">
            <img src="data:image/png;base64,{logo_base64}" alt="IBLDG logo">
        </div>
        """,
        unsafe_allow_html=True,
    )
except FileNotFoundError:
    pass

st.sidebar.title("🏢 Menu")
st.sidebar.caption("Society Maintenance Management")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["💳 Payment Tracker", "🗓️ Initialize Month", "📄 Generate Bills"],
    label_visibility="collapsed"
)

st.sidebar.divider()
st.sidebar.link_button("📊 Open Maintenance Sheets", st.secrets["connections"]["gsheets"]["spreadsheet"])


# ============================================================
# PAGE 1: Generate Bills
# ============================================================
if page == "📄 Generate Bills":
    st.header("Generate Monthly Bills")
    st.caption("Generate maintenance bills for a selected billing month.")
    st.divider()

    available_months = ledger_df["Month & Year"].dropna().unique().tolist()

    if not available_months:
        st.warning("No billing months available.")
        st.stop()

    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            selected_month = st.selectbox(
                "Billing Month",
                available_months,
                format_func=lambda x: pd.to_datetime(x, format="%d-%m-%Y").strftime("%B %Y")
            )
        
        month_label = pd.to_datetime(selected_month, format="%d-%m-%Y").strftime("%B %Y")
        default_name = f"{month_label} Dues"

        with col2:
            output_filename = st.text_input("Output File Name", value=default_name)

    output_format = st.radio(
        "Output Format",
        ["Standard PDF", "Printable PDF"],
        index=0,
        horizontal=True
    )

    st.write("") 
    if st.button("Generate Bills", type="primary"):
        with st.spinner("Generating PDF bills..."):
            pdf_file = generate_monthly_bills(
                master_df, ledger_df, selected_month, output_format=output_format
            )
    
        if pdf_file is None:
            st.error("No bills found for the selected month.")
        else:
            st.success("Bills generated successfully. You can download them below.")
            st.download_button(
                "⬇ Download PDF",
                data=pdf_file,
                file_name=f"{output_filename}.pdf",
                mime="application/pdf",
                type="primary"
            )

# ============================================================
# PAGE 2: Payment Tracker
# ============================================================
elif page == "💳 Payment Tracker":
    st.header("Payment Tracker")
    st.caption("Upload a bank statement to reconcile online maintenance payments.")
    st.divider()

    uploaded_statement = st.file_uploader("Bank Statement (PDF)", type=["pdf"])

    if uploaded_statement and st.button("Generate Reconciliation", type="primary"):
        with st.spinner("Analyzing bank statement..."):
            statement_month = get_statement_month(uploaded_statement)
            month_name = pd.to_datetime(statement_month, dayfirst=True).strftime("%B %Y")
            raw_bank_df = extract_bank_statement(uploaded_statement)
            grouped_payments, unmapped_df = map_bank_to_rooms(raw_bank_df, master_df)
            
            month_ledger = ledger_df[ledger_df["Month & Year"] == statement_month].copy()

            if month_ledger.empty:
                st.error(f"No ledger found for {month_name}.")
                st.stop()

            report_df = generate_reconciliation_report(grouped_payments, master_df, month_ledger)

            st.session_state.statement_month = statement_month
            st.session_state.report_df = report_df
            st.session_state.raw_bank_df = raw_bank_df
            st.session_state.grouped_payments = grouped_payments
            st.session_state.unmapped_df = unmapped_df
            st.session_state.reconciliation_done = True
            st.session_state.status_updated = False

    if st.session_state.reconciliation_done:
        report_df = st.session_state.report_df
        raw_bank_df = st.session_state.raw_bank_df
        grouped_payments = st.session_state.grouped_payments
        unmapped_df = st.session_state.unmapped_df
        statement_month = st.session_state.statement_month

        month_name = pd.to_datetime(statement_month, dayfirst=True).strftime("%B %Y")
        st.info(f"Statement Month : **{month_name}**", icon="📅")

        paid = (report_df["Status"] == "Paid").sum()
        partial = (report_df["Status"] == "Partially Paid").sum()
        unpaid = (report_df["Status"] == "Unpaid").sum()

        total_credit = raw_bank_df["Credit"].sum()
        matched_credit = grouped_payments["Total_Paid"].sum()
        unmatched_credit = unmapped_df["Credit"].sum()

        # Status Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Paid", paid)
        col2.metric("🟠 Partially Paid", partial)
        col3.metric("🔴 Unpaid", unpaid)

        st.divider()
        st.subheader("Payment Summary")
        st.caption("Only online payments are reconciled automatically. Verify cash manually.")

        # Financial Metrics
        col4, col5, col6 = st.columns(3)
        col4.metric("Total Credits", f"₹{total_credit:,.0f}")
        col5.metric("Matched Credits", f"₹{matched_credit:,.0f}")
        col6.metric("Unmatched Credits", f"₹{unmatched_credit:,.0f}")

        st.divider()
        st.subheader("Reconciliation Report")
        # CHANGED: use_container_width -> width="stretch"
        st.dataframe(report_df, width="stretch")

        st.divider()
        st.subheader("Unmatched Transactions")
        st.dataframe(unmapped_df, width="stretch")

        st.divider()
        if st.button("Update Status to Google Sheets", type="primary"):
            update_status_to_sheet(report_df, statement_month)
            st.session_state.status_updated = True

        if st.session_state.status_updated:
            st.success("Status and settlement have been updated successfully.")
            st.caption("Verify cash payments in Google Sheets, then continue with Initialize Billing Month.")

# ============================================================
# PAGE 3: Initialize Billing Month
# ============================================================
elif page == "🗓️ Initialize Month":
    st.header("Initialize Billing Month")
    st.caption("Create the next billing cycle after all payment statuses are verified.")
    st.divider()

    st.session_state.setdefault("initialization_success", False)
    st.session_state.setdefault("initialized_month", None)
    st.session_state.setdefault("initialization_current_month", None)

    available_months = ledger_df["Month & Year"].dropna().unique().tolist()

    selected_month = st.selectbox(
        "Current Billing Month",
        available_months,
        format_func=lambda x: pd.to_datetime(x, dayfirst=True).strftime("%B %Y")
    )

    st.write("")
    if st.button("Validate", type="primary"):
        latest_ledger_df = conn.read(worksheet="testData", ttl=0)
        latest_ledger_df.columns = latest_ledger_df.columns.str.strip()

        current_month_df = latest_ledger_df[
            latest_ledger_df["Month & Year"] == selected_month
        ].copy()

        next_month = get_next_month(selected_month)
        validation = validate_initialization(current_month_df, latest_ledger_df, next_month)

        st.session_state.validation = validation
        st.session_state.current_month_df = current_month_df
        st.session_state.next_month = next_month
        st.session_state.new_month_df = None
        st.session_state.initialization_success = False
        st.session_state.initialized_month = None
        st.session_state.initialization_current_month = selected_month

    if st.session_state.validation is not None:
        validation = st.session_state.validation
        st.divider()

        if not validation["current_month_exists"]:
            st.error("Current month does not exist in testData.")
        if validation["blank_status"] > 0:
            st.error(f"{validation['blank_status']} flats have blank status.")
        if validation["month_exists"]:
            st.error("Next month already exists.")

        if validation["valid"]:
            current_month_label = pd.to_datetime(
                st.session_state.initialization_current_month, dayfirst=True
            ).strftime("%B %Y")
            next_month_label = pd.to_datetime(
                st.session_state.next_month, dayfirst=True
            ).strftime("%B %Y")

            st.subheader("Initialization Summary")
            # Using 4 columns in wide layout ensures nothing collapses
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current Month", current_month_label)
            c2.metric("Next Month", next_month_label)
            c3.metric("Total Flats", len(st.session_state.current_month_df))
            c4.metric("Status", "Ready")

            new_month_df = prepare_new_month_dataframe(
                st.session_state.current_month_df, st.session_state.next_month
            )
            st.session_state.new_month_df = new_month_df

            st.divider()
            print(new_month_df.columns.tolist())
            preview_df = new_month_df.copy()

            preview_df = preview_df.merge(
                master_df[["Room No", "Name"]],
                on="Room No",
                how="left"
            )
            
            preview_df = preview_df[
                (preview_df["Previous dues"] > 0)
                | (preview_df["Balance Advance"] > 0)
                | (preview_df["Adjustment"] > 0)
            ]

            preview_columns = [
                "Room No",
                "Name",
                "Previous dues",
                "Adjustment",
                "Balance Advance",
            ]

            preview_df = preview_df[preview_columns]
            st.subheader("Next Month Preview")

            if preview_df.empty:
                st.success("No carry-forward balances found.")
            else:
                st.dataframe(preview_df,width="stretch",hide_index=True)

            st.caption("Only flats with Previous Dues, Adjustment, or Balance Advance are shown for verification.")
            st.info(
                f"""
                Flats : {len(new_month_df)}

                Carry Forward : {len(preview_df)}
                """
            )

            if st.button("🚀 Initialize Month", type="primary"):
                append_to_ledger(st.session_state.new_month_df)
                st.session_state.initialization_success = True
                st.session_state.initialized_month = pd.to_datetime(
                    st.session_state.next_month, dayfirst=True
                ).strftime("%B %Y")
                st.session_state.validation = None

    if st.session_state.initialization_success:
        st.success(f"{st.session_state.initialized_month} initialized successfully.")
        st.caption("Review the initialized month in Google Sheets before generating bills.")
