import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

from utils.generator import generate_monthly_bills
from utils.reconciler import (
    extract_bank_statement,
    map_bank_to_rooms,
    generate_reconciliation_report
)

from utils.initializer import (
    get_next_month,
    prepare_new_month_dataframe
)

from utils.sheets import append_to_ledger
from utils.helpers import get_statement_month

st.set_page_config(
    page_title="Maintenance Billing System", page_icon="🏢", layout="wide"
)

# --------------------------
# Load CSS
# --------------------------
try:
    with open("assets/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

st.title("🏢 Maintenance Billing System")
st.caption("Generate Monthly Maintenance Bills")

# --------------------------
# Session State
# --------------------------
if "report_df" not in st.session_state:
    st.session_state.report_df = None

if "new_month_df" not in st.session_state:
    st.session_state.new_month_df = None

if "statement_month" not in st.session_state:
    st.session_state.statement_month = None

if "next_month" not in st.session_state:
    st.session_state.next_month = None

if "month_exists" not in st.session_state:
    st.session_state.month_exists = None

if "reconciliation_done" not in st.session_state:
    st.session_state.reconciliation_done = False

# --------------------------
# Google Sheets Connection
# --------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)

    master_df = conn.read(worksheet="Master_Flats",
    ttl=0)
    # ledger_df = conn.read(worksheet="Yearly_Ledger")
    ledger_df = conn.read(worksheet="testData",
    ttl=0)

    st.toast("✅ Google Sheets Connected")

except Exception as e:
    st.error(f"Connection Failed\n\n{e}")
    st.stop()

# --------------------------
# Tabs
# --------------------------
tab1, tab2, tab3 = st.tabs(
    ["🗓️ Initialize Month", "📄 Generate Bills", "💰 Payment Tracker"]
)

# ============================================================
# TAB 1
# ============================================================

with tab1:

    st.header("Initialize Billing Month")
    st.caption(
        "Create the next billing month after verifying the reconciliation report."
    )

    SHEET_URL = st.secrets["connections"]["gsheets"]["spreadsheet"]

    st.link_button(
        "📊 Open Google Sheets",
        SHEET_URL,
        use_container_width=True
    )

    st.divider()

    st.warning(
        """
        **Workflow**

        1. Complete Payment Reconciliation.
        2. Verify the report.
        3. Initialize Next Month.
        4. Review Google Sheet.
        5. Generate Bills.
        """
    )

    initialize_btn = st.button(
        "🚀 Initialize Next Month",
        disabled=True,
        use_container_width=True
    )

    st.caption(
        "This button will automatically activate after a successful reconciliation."
    )
# ============================================================
# TAB 2
# ============================================================

with tab2:

    st.header("Generate Monthly Bills")

    available_months = ledger_df["Month & Year"].dropna().unique().tolist()

    if len(available_months) == 0:
        st.warning("No Months Found.")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:

        selected_month = st.selectbox("Select Billing Month", available_months)

    with col2:
        try:
            month_name = pd.to_datetime(
                selected_month,
                dayfirst=True
            ).strftime("%B")
        except Exception:
            month_name = str(selected_month)

        default_name = f"{month_name} Dues"

        output_filename = st.text_input("Output PDF Name", value=default_name)

    st.divider()

    if st.button("Generate Bills", type="primary", use_container_width=True):

        with st.spinner("Generating Bills..."):

            pdf_file = generate_monthly_bills(master_df, ledger_df, selected_month)

        if pdf_file is None:

            st.error("No Bills Found.")

        else:

            st.success("Bills Generated Successfully")

            st.download_button(
                "⬇ Download PDF",
                data=pdf_file,
                file_name=f"{output_filename}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

# ============================================================
# TAB 3
# ============================================================

with tab3:

    st.header("Payment Tracker")
    st.caption(
        "Upload Bank Statement and Verify Maintenance Payments"
    )

    uploaded_statement = st.file_uploader(
        "Upload Bank Statement (PDF)",
        type=["pdf"]
    )

    if uploaded_statement is not None:

        if st.button(
            "Generate Reconciliation Report",
            type="primary",
            use_container_width=True
        ):

            with st.spinner(
                "Analyzing Bank Statement..."
            ):

                # ---------------------------------
                # Detect Statement Month
                # ---------------------------------
                statement_month = get_statement_month(
                    uploaded_statement
                )

                month_name = pd.to_datetime(
                    statement_month,
                    dayfirst=True
                ).strftime("%B %Y")

                # ---------------------------------
                # Extract Bank Statement
                # ---------------------------------
                raw_bank_df = extract_bank_statement(
                    uploaded_statement
                )

                # ---------------------------------
                # Map Payments
                # ---------------------------------
                grouped_payments, unmapped_df = (
                    map_bank_to_rooms(
                        raw_bank_df,
                        master_df
                    )
                )

                # ---------------------------------
                # Ledger for Statement Month
                # ---------------------------------
                month_ledger = ledger_df[
                    ledger_df["Month & Year"] == statement_month
                ].copy()

                if month_ledger.empty:

                    st.error(
                        f"No ledger found for {month_name}."
                    )

                    st.stop()

                # ---------------------------------
                # Reconciliation
                # ---------------------------------
                report_df = (
                    generate_reconciliation_report(
                        grouped_payments,
                        master_df,
                        month_ledger
                    )
                )

                # ---------------------------------
                # Save Session
                # ---------------------------------
                st.session_state.statement_month = (
                    statement_month
                )

                st.session_state.report_df = (
                    report_df
                )

                st.session_state.raw_bank_df = (
                    raw_bank_df
                )

                st.session_state.grouped_payments = (
                    grouped_payments
                )

                st.session_state.unmapped_df = (
                    unmapped_df
                )

                st.session_state.reconciliation_done = (
                    True
                )

            st.toast(
                "Reconciliation completed successfully."
            )

    # -------------------------------------------------
    # Show Saved Reconciliation
    # -------------------------------------------------

    if st.session_state.reconciliation_done:

        report_df = st.session_state.report_df

        raw_bank_df = st.session_state.raw_bank_df

        grouped_payments = (
            st.session_state.grouped_payments
        )

        unmapped_df = (
            st.session_state.unmapped_df
        )

        statement_month = (
            st.session_state.statement_month
        )

        month_name = pd.to_datetime(
            statement_month,
            dayfirst=True
        ).strftime("%B %Y")

        st.info(
            f"Statement Month : {month_name}"
        )

        # ---------------------------------
        # Summary
        # ---------------------------------

        paid = (
            report_df["Status"] == "Paid"
        ).sum()

        partial = (
            report_df["Status"] == "Partially Paid"
        ).sum()

        unpaid = (
            report_df["Status"] == "Unpaid"
        ).sum()

        total_credit = (
            raw_bank_df["Credit"].sum()
        )

        matched_credit = (
            grouped_payments["Total_Paid"].sum()
        )

        unmatched_credit = (
            unmapped_df["Credit"].sum()
        )

        difference = total_credit - (
            matched_credit + unmatched_credit
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Paid",
            paid
        )

        col2.metric(
            "Partial",
            partial
        )

        col3.metric(
            "Unpaid",
            unpaid
        )

        st.divider()

        st.subheader(
            "Payment Summary"
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Total Credits",
            f"₹{total_credit:,.0f}"
        )

        c2.metric(
            "Matched Credits",
            f"₹{matched_credit:,.0f}"
        )

        c3.metric(
            "Unmatched Credits",
            f"₹{unmatched_credit:,.0f}"
        )

        if difference != 0:

            st.warning(
                f"₹{difference:,.0f} could not be reconciled."
            )

        st.divider()

        st.subheader(
            "Reconciliation Report"
        )

        st.dataframe(
            report_df,
            use_container_width=True
        )

        if not unmapped_df.empty:

            st.divider()

            st.subheader(
                "Unmatched Transactions"
            )

            st.dataframe(
                unmapped_df,
                use_container_width=True
            )

            st.divider()

        