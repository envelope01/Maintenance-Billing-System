import os
import tempfile
import subprocess
import pandas as pd
import streamlit as st
import base64
import streamlit.components.v1 as components
from docxtpl import DocxTemplate
from pypdf import PdfWriter

# ==========================================
# STREAMLIT PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Billing PDF Generator",
    layout="wide"
)

st.title("Billing PDF Generator")

# ==========================================
# FILE UPLOADS
# ==========================================
uploaded_excel = st.file_uploader("Upload Excel File", type=["xlsx"])
uploaded_template = st.file_uploader("Upload Word Template", type=["docx"])

# ==========================================
# AFTER EXCEL UPLOAD SHOW SHEETS
# ==========================================
if uploaded_excel is not None:
    excel_data = pd.ExcelFile(uploaded_excel)
    selected_sheet = st.selectbox("Select Sheet", excel_data.sheet_names)
    
    default_pdf_name = f"{selected_sheet} Dues"
    pdf_name = st.text_input("Rename Final PDF (without .pdf)", value=default_pdf_name)

    if st.button("Generate Bills"):
        
        if uploaded_template is None:
            st.error("Please upload Template.docx")
            st.stop()

        with tempfile.TemporaryDirectory() as temp_dir:

            # ==========================================
            # SAVE UPLOADED FILES
            # ==========================================
            excel_path = os.path.join(temp_dir, "uploaded_excel.xlsx")
            template_path = os.path.join(temp_dir, "Template.docx")

            with open(excel_path, "wb") as f:
                f.write(uploaded_excel.getbuffer())

            with open(template_path, "wb") as f:
                f.write(uploaded_template.getbuffer())

            # ==========================================
            # LOAD AND CLEAN DATA
            # ==========================================
            df = pd.read_excel(excel_path, sheet_name=selected_sheet)
            df.columns = df.columns.str.strip()

            columns_to_drop = ['Sr. No', 'Recd Advance', 'Current Bill Amt']
            df = df.drop(columns=[col for col in columns_to_drop if col in df.columns], errors='ignore')
            df = df.fillna(0)

            # ==========================================
            # DEFINE EXPLICIT DICTIONARY MAP
            # ==========================================
            mapping = {
                'Name': 'Name',
                'Room No': 'Room_No',
                'Bill No': 'Bill_No',
                'Service M Chrg.': 'Service_M_Chrg',
                'Sinking Fund': 'Sinking_Fund',
                'Repair & Maintenance': 'Repair__Maintenance',
                'Edu.': 'Edu',
                'NOC': 'NOC',
                'Parking': 'Parking_',
                'Other': 'Other_',
                'Regular Dues': 'Regular_Dues',
                'Previous dues': 'Previous_dues',
                'Late Chrg / Panelty': 'Late_Chrg__Panelty',
                'Adjustment': 'Adjustment',
                'Balance Advance': 'Balance_Advance',
                'Total Dues': 'Total_Dues'
            }

            # ==========================================
            # TEMP FOLDERS
            # ==========================================
            docx_dir = os.path.join(temp_dir, "temp_docx_files")
            pdf_dir = os.path.join(temp_dir, "temp_pdf_files")

            os.makedirs(docx_dir, exist_ok=True)
            os.makedirs(pdf_dir, exist_ok=True)

            temp_docx_list = []
            temp_pdf_list = []

            # ==========================================
            # GENERATE DOCX FILES
            # ==========================================
            for index, row in df.iterrows():
                row_dict = row.to_dict()
                context = {}

                for excel_header, word_placeholder in mapping.items():
                    if excel_header in row_dict:
                        value = row_dict[excel_header]

                        if isinstance(value, (int, float)) and word_placeholder not in ['Room_No', 'Bill_No']:
                            context[word_placeholder] = f"{value:.0f}"
                        else:
                            context[word_placeholder] = str(value)

                doc = DocxTemplate(template_path)
                doc.render(context)

                docx_file = os.path.abspath(os.path.join(docx_dir, f"bill_{index}.docx"))
                doc.save(docx_file)
                temp_docx_list.append(docx_file)

            # ==========================================
            # CONVERT DOCX TO PDF USING LIBREOFFICE (Linux Safe)
            # ==========================================
            for index, docx_path in enumerate(temp_docx_list):
                subprocess.run(
                    [
                        "libreoffice",  # Using 'libreoffice' command instead of 'soffice' for Linux
                        "--headless",
                        "--convert-to",
                        "pdf",
                        docx_path,
                        "--outdir",
                        pdf_dir
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                generated_pdf = os.path.join(pdf_dir, f"bill_{index}.pdf")
                temp_pdf_list.append(generated_pdf)

            # ==========================================
            # MERGE PDFs
            # ==========================================
            merger = PdfWriter()

            for pdf_path in temp_pdf_list:
                merger.append(pdf_path)

            final_pdf_name = f"{pdf_name}.pdf"
            final_pdf_path = os.path.join(temp_dir, final_pdf_name)

            merger.write(final_pdf_path)
            merger.close()

            # ==========================================
            # DIRECT DOWNLOAD WORKAROUND (Base64 + JS)
            # ==========================================
            with open(final_pdf_path, "rb") as f:
                pdf_bytes = f.read()
                b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # JS script jo automatic download trigger karega
            js_download = f"""
                <a id="auto-download" href="data:application/pdf;base64,{b64_pdf}" download="{final_pdf_name}"></a>
                <script>
                    document.getElementById('auto-download').click();
                </script>
            """
            
            # Render the hidden HTML component
            components.html(js_download, height=0)