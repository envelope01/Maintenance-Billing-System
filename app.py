import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

from utils.generator import generate_monthly_bills
from utils.reconciler import (
    extract_bank_statement,
    map_bank_to_rooms,
    generate_reconciliation_report
)

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
# Google Sheets Connection
# --------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)

    master_df = conn.read(worksheet="Master_Flats")
    ledger_df = conn.read(worksheet="Yearly_Ledger")

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
    st.info("Coming Soon")

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
    st.caption("Upload Bank Statement and Verify Maintenance Payments")

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

            with st.spinner("Analyzing Bank Statement..."):

                # Detect Statement Month
                statement_month = get_statement_month(
                    uploaded_statement
                )

                month_name = pd.to_datetime(
                    statement_month,
                    dayfirst=True
                ).strftime("%B %Y")

                st.caption(
                    f"Statement Month Detected : {month_name}"
                )

                # Extract Transactions
                raw_bank_df = extract_bank_statement(
                    uploaded_statement
                )

                # Match Transactions
                grouped_payments, unmapped_df = map_bank_to_rooms(
                    raw_bank_df,
                    master_df
                )

                # Filter Ledger
                month_ledger = ledger_df[
                    ledger_df["Month & Year"] == statement_month
                ].copy()

                if month_ledger.empty:

                    st.error(
                        f"No ledger found for {month_name}."
                    )

                    st.stop()

                # Generate Report
                report_df = generate_reconciliation_report(
                    grouped_payments,
                    master_df,
                    month_ledger
                )

            st.toast("Reconciliation completed successfully.")

            # -------------------------------------------------
            # Summary
            # -------------------------------------------------

            paid = (
                report_df["Status"] == "Paid"
            ).sum()

            partial = (
                report_df["Status"] == "Partially Paid"
            ).sum()

            unpaid = (
                report_df["Status"] == "Unpaid"
            ).sum()

            col1, col2, col3 = st.columns(3)

            col1.metric("Paid", paid)
            col2.metric("Partial", partial)
            col3.metric("Unpaid", unpaid)

            st.divider()

            # -------------------------------------------------
            # Report
            # -------------------------------------------------

            st.subheader("Reconciliation Report")

            st.dataframe(
                report_df,
                use_container_width=True
            )

            st.divider()

            # -------------------------------------------------
            # Unmatched Transactions
            # -------------------------------------------------

            if not unmapped_df.empty:

                st.subheader("Unmatched Transactions")

                st.dataframe(
                    unmapped_df,
                    use_container_width=True
                )