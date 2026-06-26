import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

from utils.generator import generate_monthly_bills

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
    st.info("Coming Soon")
