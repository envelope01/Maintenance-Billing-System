import os
import io
import shutil

import pandas as pd
import numpy as np

from docxtpl import DocxTemplate
from PyPDF2 import PdfMerger

from utils.config import MAPPING
from utils.helpers import get_billing_dates, format_amount
from utils.converter import convert_docx_to_pdf, detect_pdf_engine


def generate_monthly_bills(master_df, ledger_df, selected_month):

    # ---------------------------------
    # Clean columns
    # ---------------------------------
    master_df = master_df.copy()
    ledger_df = ledger_df.copy()

    master_df.columns = master_df.columns.str.strip()
    ledger_df.columns = ledger_df.columns.str.strip()

    master_df["Room No"] = master_df["Room No"].astype(str).str.strip()
    ledger_df["Room No"] = ledger_df["Room No"].astype(str).str.strip()

    # ---------------------------------
    # Filter selected month
    # ---------------------------------
    month_data = ledger_df[
        ledger_df["Month & Year"] == selected_month
    ].copy()

    if month_data.empty:
        return None

    # ---------------------------------
    # Merge master + ledger
    # ---------------------------------
    merged_df = pd.merge(
        month_data,
        master_df,
        on="Room No",
        how="left"
    )

    merged_df.replace(
        ["NaN", "", None],
        np.nan,
        inplace=True
    )

    template_path = "assets/Template.docx"

    merger = PdfMerger()

    engine = detect_pdf_engine()

    word_app = None

    try:

        # ---------------------------------
        # Start MS Word once
        # ---------------------------------
        if engine == "word":

            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()

            word_app = win32com.client.Dispatch(
                "Word.Application"
                )

            word_app.Visible = False

        # ---------------------------------
        # Temporary folder
        # ---------------------------------
        temp_dir = os.path.abspath("temp_bills")
        os.makedirs(temp_dir, exist_ok=True)

        for _, row in merged_df.iterrows():

            room_no = str(
                row.get("Room No", "Unknown")
                ).strip()

            try:

                doc = DocxTemplate(template_path)

                context = get_billing_dates(selected_month)

                for df_col, placeholder in MAPPING.items():

                    value = row.get(df_col, np.nan)

                    if df_col in ["Name", "Room No", "Extra Charges"]:
                        context[placeholder] = (
                            str(value).strip()
                            if pd.notna(value)
                            else ""
                        )
                    elif df_col == "Bill No":
                        context[placeholder] = (
                            str(int(value))
                            if pd.notna(value)
                            else ""
                        )

                    else:
                        context[placeholder] = format_amount(value)

                doc.render(context)

                docx_path = os.path.join(
                    temp_dir,
                    f"bill_{room_no}.docx"
                )

                doc.save(docx_path)

                pdf_path = convert_docx_to_pdf(
                    docx_path,
                    temp_dir,
                    engine=engine,
                    word_app=word_app
                )

                if not os.path.exists(pdf_path):
                    raise FileNotFoundError(
                        f"PDF was not generated:\n{pdf_path}"
                    )

                merger.append(pdf_path)

            except Exception as e:

                raise RuntimeError(
                    f"Error generating bill for Room {room_no}\n\n{e}"
                )

        output_pdf = io.BytesIO()

        merger.write(output_pdf)
        output_pdf.seek(0)
        merger.close()

        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        return output_pdf

    finally:

        if word_app is not None:
            try:
                word_app.Quit()
            finally:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass