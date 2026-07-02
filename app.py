import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from utils.generator import generate_monthly_bills
from utils.helpers import get_statement_month
from utils.initializer import get_next_month, prepare_new_month_dataframe,validate_initialization
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

st.set_page_config(
    page_title="Maintenance Billing System",
    page_icon="🏢",
    layout="wide"
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
# Application Header
# --------------------------------------------------

st.title("🏢 Maintenance Billing System")
st.caption("Society Maintenance Billing & Payment Management")

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
    ledger_df = conn.read(worksheet="Yearly_Ledger", ttl=0)

except Exception as e:
    st.error(f"Google Sheets Connection Failed\n\n{e}")
    st.stop()

# --------------------------
# Tabs
# --------------------------
tab1, tab2, tab3 = st.tabs(
    ["📄 Generate Bills", "💳 Payment Tracker", "🗓️ Initialize Month"]
)

# ============================================================
# TAB 1
# ============================================================

with tab1:

    st.header("Generate Monthly Bills")
    st.caption("Generate maintenance bills for a selected billing month.")

    available_months = ledger_df["Month & Year"].dropna().unique().tolist()

    if not available_months:
        st.warning("No billing months available.")
        st.stop()

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_month = st.selectbox(
            "Billing Month",
            available_months,
            format_func=lambda x: pd.to_datetime(x, dayfirst=True).strftime("%B %Y")
        )

    month_label = pd.to_datetime(selected_month, dayfirst=True).strftime("%B %Y")
    default_name = f"{month_label} Dues"

    with col2:
        output_filename = st.text_input(
            "Output File Name",
            value=default_name
        )

    if st.button("Generate Bills", type="primary"):

        with st.spinner("Generating PDF bills..."):
            pdf_file = generate_monthly_bills(
                master_df,
                ledger_df,
                selected_month
            )

        if pdf_file is None:
            st.error("No bills found for the selected month.")
        else:
            st.toast("Bills generated successfully.")

            st.download_button(
                "⬇ Download PDF",
                data=pdf_file,
                file_name=f"{output_filename}.pdf",
                mime="application/pdf"
            )


# ============================================================
# TAB 2
# ============================================================

with tab2:

    st.header("Payment Tracker")
    st.caption("Upload a bank statement to reconcile online maintenance payments.")

    uploaded_statement = st.file_uploader(
        "Bank Statement (PDF)",
        type=["pdf"]
    )

    if uploaded_statement and st.button("Generate Reconciliation", type="primary"):

        with st.spinner("Analyzing bank statement..."):

            statement_month = get_statement_month(uploaded_statement)
            month_name = pd.to_datetime(statement_month, dayfirst=True).strftime("%B %Y")

            raw_bank_df = extract_bank_statement(uploaded_statement)

            grouped_payments, unmapped_df = map_bank_to_rooms(
                raw_bank_df,
                master_df
            )

            month_ledger = ledger_df[
                ledger_df["Month & Year"] == statement_month
            ].copy()

            if month_ledger.empty:
                st.error(f"No ledger found for {month_name}.")
                st.stop()

            report_df = generate_reconciliation_report(
                grouped_payments,
                master_df,
                month_ledger
            )

            st.session_state.statement_month = statement_month
            st.session_state.report_df = report_df
            st.session_state.raw_bank_df = raw_bank_df
            st.session_state.grouped_payments = grouped_payments
            st.session_state.unmapped_df = unmapped_df
            st.session_state.reconciliation_done = True

        st.toast("Reconciliation completed successfully.")

    if st.session_state.reconciliation_done:

        report_df = st.session_state.report_df
        raw_bank_df = st.session_state.raw_bank_df
        grouped_payments = st.session_state.grouped_payments
        unmapped_df = st.session_state.unmapped_df
        statement_month = st.session_state.statement_month

        month_name = pd.to_datetime(statement_month, dayfirst=True).strftime("%B %Y")

        st.info(f"Statement Month : {month_name}")

        paid = (report_df["Status"] == "Paid").sum()
        partial = (report_df["Status"] == "Partially Paid").sum()
        unpaid = (report_df["Status"] == "Unpaid").sum()

        total_credit = raw_bank_df["Credit"].sum()
        matched_credit = grouped_payments["Total_Paid"].sum()
        unmatched_credit = unmapped_df["Credit"].sum()

        difference = total_credit - (
            matched_credit + unmatched_credit
        )

        col1, col2, col3 = st.columns(3)

        col1.metric("Paid", paid)
        col2.metric("Partial", partial)
        col3.metric("Unpaid", unpaid)

        st.divider()
    
        st.subheader("Payment Summary")

        st.caption(
            "Only online payments are reconciled automatically. Cash payments must be verified manually."
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Total Credits",
            f"₹{total_credit:,.0f}"
        )

        col2.metric(
            "Matched Credits",
            f"₹{matched_credit:,.0f}"
        )

        col3.metric(
            "Unmatched Credits",
            f"₹{unmatched_credit:,.0f}"
        )

        st.divider()

        st.subheader("Reconciliation Report")

        st.dataframe(
            report_df,
            use_container_width=True
        )

        st.divider()

        if not unmapped_df.empty:

            st.subheader("Unmatched Transactions")

            st.dataframe(
                unmapped_df,
                use_container_width=True
            )

            st.divider()

        if difference != 0:

            st.warning(
                f"₹{difference:,.0f} could not be reconciled."
            )

        if st.button(
            "📤 Update Status",
            type="primary"
        ):

            update_status_to_sheet(
                report_df,
                statement_month
            )

            st.session_state.status_updated = True

            st.toast(
                "Online payment statuses updated successfully."
            )

        if st.session_state.status_updated:

            st.success(
                "Online payment statuses have been updated."
            )

            st.link_button(
                "📊 Open Google Sheets",
                st.secrets["connections"]["gsheets"]["spreadsheet"]
            )

            st.caption(
                "Verify cash payments in Google Sheets, then return to the Initialize Billing Month tab."
            )


# ============================================================
# TAB 3
# ============================================================

with tab3:
    st.header("Initialize Billing Month")
    st.caption("Create the next billing cycle after all payment statuses are verified.")

    available_months = ledger_df["Month & Year"].dropna().unique().tolist()

    selected_month = st.selectbox(
        "Current Billing Month",
        available_months,
        format_func=lambda x: pd.to_datetime(x, dayfirst=True).strftime("%B %Y")
    )

    if st.button("Validate", type="primary"):

        current_month_df = ledger_df[
            ledger_df["Month & Year"] == selected_month
        ].copy()

        next_month = get_next_month(selected_month)

        validation = validate_initialization(
            current_month_df,
            ledger_df,
            next_month
        )

        st.session_state.validation = validation
        st.session_state.current_month_df = current_month_df
        st.session_state.next_month = next_month

    if st.session_state.validation is not None:

        validation = st.session_state.validation

        st.divider()

        st.subheader("Validation Summary")

        col1, col2 = st.columns(2)

        with col1:

            if validation["blank_status"] == 0:
                st.success("All payment statuses are updated.")
            else:
                st.error(
                    f"{validation['blank_status']} flats have blank status."
                )

        with col2:

            if validation["month_exists"]:
                st.error("Next month already exists.")
            else:

                month_name = pd.to_datetime(
                    st.session_state.next_month,
                    dayfirst=True
                ).strftime("%B %Y")

                st.success(
                    f"{month_name} is ready to initialize."
                )

        if validation["valid"]:

            new_month_df = prepare_new_month_dataframe(
                st.session_state.current_month_df,
                st.session_state.next_month
            )

            st.session_state.new_month_df = new_month_df

            st.divider()

            st.subheader("Next Month Preview")

            st.dataframe(
                new_month_df,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "Please verify all cash payments in Google Sheets before initializing the next billing month."
            )

            if st.button(
                "🚀 Initialize Month",
                type="primary"
            ):

                append_to_ledger(
                    st.session_state.new_month_df
                )
                st.session_state.validation = None

                st.toast(
                    f"{pd.to_datetime(st.session_state.next_month, dayfirst=True).strftime('%B %Y')} initialized successfully."
                )

                st.rerun()