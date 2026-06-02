import os
import tempfile
import subprocess
import pandas as pd
import streamlit as st
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
uploaded_excel = st.file_uploader(
    "Upload Excel File",
    type=["xlsx"]
)

uploaded_template = st.file_uploader(
    "Upload Word Template",
    type=["docx"]
)

# ==========================================
# AFTER EXCEL UPLOAD SHOW SHEETS
# ==========================================
if uploaded_excel is not None:

    excel_data = pd.ExcelFile(uploaded_excel)

    selected_sheet = st.selectbox(
        "Select Sheet",
        excel_data.sheet_names
    )

    default_pdf_name = f"{selected_sheet} Dues"

    pdf_name = st.text_input(
        "Rename Final PDF (without .pdf)",
        value=default_pdf_name
    )

    if st.button("Generate Bills"):

        if uploaded_template is None:
            st.error("Please upload Template.docx")
            st.stop()

        with tempfile.TemporaryDirectory() as temp_dir:

            # ==========================================
            # SAVE UPLOADED FILES
            # ==========================================
            excel_path = os.path.join(
                temp_dir,
                "uploaded_excel.xlsx"
            )

            template_path = os.path.join(
                temp_dir,
                "Template.docx"
            )

            with open(excel_path, "wb") as f:
                f.write(uploaded_excel.getbuffer())

            with open(template_path, "wb") as f:
                f.write(uploaded_template.getbuffer())

            # ==========================================
            # LOAD DATA
            # ==========================================
            df = pd.read_excel(
                excel_path,
                sheet_name=selected_sheet
            )

            columns_to_drop = [
                'Sr. No',
                'Recd Advance',
                'Current Bill Amt'
            ]

            df = df.drop(
                columns=columns_to_drop,
                errors='ignore'
            )

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
                'Parking ': 'Parking_',
                'Other ': 'Other_',
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
            docx_dir = os.path.join(
                temp_dir,
                "temp_docx_files"
            )

            pdf_dir = os.path.join(
                temp_dir,
                "temp_pdf_files"
            )

            os.makedirs(docx_dir, exist_ok=True)
            os.makedirs(pdf_dir, exist_ok=True)

            temp_docx_list = []
            temp_pdf_list = []

            st.info("Step 1: Generating Word files...")

            progress_bar = st.progress(0)

            # ==========================================
            # GENERATE DOCX FILES
            # ==========================================
            total_rows = len(df)

            for index, row in df.iterrows():

                row_dict = row.to_dict()
                context = {}

                for excel_header, word_placeholder in mapping.items():

                    if excel_header in row_dict:

                        value = row_dict[excel_header]

                        if (
                            isinstance(value, (int, float))
                            and word_placeholder not in ['Room_No', 'Bill_No']
                        ):
                            context[word_placeholder] = f"{value:.0f}"
                        else:
                            context[word_placeholder] = str(value)

                doc = DocxTemplate(template_path)
                doc.render(context)

                docx_file = os.path.abspath(
                    os.path.join(
                        docx_dir,
                        f"bill_{index}.docx"
                    )
                )

                doc.save(docx_file)

                temp_docx_list.append(docx_file)

                progress_bar.progress(
                    (index + 1) / total_rows
                )

            st.success(
                f"Generated {len(temp_docx_list)} Word files"
            )

            # ==========================================
            # CONVERT DOCX TO PDF USING LIBREOFFICE
            # ==========================================
            st.info("Step 2: Converting Word files to PDFs...")

            for index, docx_path in enumerate(temp_docx_list):

                subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        docx_path,
                        "--outdir",
                        pdf_dir
                    ],
                    check=True
                )

                generated_pdf = os.path.join(
                    pdf_dir,
                    f"bill_{index}.pdf"
                )

                temp_pdf_list.append(generated_pdf)

            # ==========================================
            # MERGE PDFs
            # ==========================================
            st.info("Step 3: Merging PDFs...")

            merger = PdfWriter()

            for pdf_path in temp_pdf_list:
                merger.append(pdf_path)

            final_pdf_name = f"{pdf_name}.pdf"

            final_pdf_path = os.path.join(
                temp_dir,
                final_pdf_name
            )

            merger.write(final_pdf_path)
            merger.close()

            st.success(
                f"SUCCESS! Generated {final_pdf_name}"
            )

            # ==========================================
            # DOWNLOAD BUTTON
            # ==========================================
            with open(final_pdf_path, "rb") as pdf_file:

                st.download_button(
                    label="Download Final PDF",
                    data=pdf_file,
                    file_name=final_pdf_name,
                    mime="application/pdf"
                )