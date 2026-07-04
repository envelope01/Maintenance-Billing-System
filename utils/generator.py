import os
import io
import shutil

import numpy as np
import pandas as pd

from docxtpl import DocxTemplate

from pypdf import PdfMerger

from utils.config import MAPPING
from utils.helpers import get_billing_dates, format_amount
from utils.converter import convert_docx_to_pdf, detect_pdf_engine

import fitz


def merge_bill_pdfs(pdf_paths):
    merger = PdfMerger()

    try:
        for pdf_path in pdf_paths:
            merger.append(pdf_path)

        output_pdf = io.BytesIO()
        merger.write(output_pdf)
        output_pdf.seek(0)

        return output_pdf

    finally:
        merger.close()



def create_printable_pdf(pdf_paths):

    output_doc = fitz.open()

    a4 = fitz.paper_rect("a4")

    # Landscape page
    page_width = a4.height
    page_height = a4.width

    margin = 15
    gap = 10

    slot_width = (page_width - (2 * margin) - gap) / 2
    slot_height = page_height - (2 * margin)

    left_rect = fitz.Rect(
        margin,
        margin,
        margin + slot_width,
        margin + slot_height
    )

    right_rect = fitz.Rect(
        margin + slot_width + gap,
        margin,
        page_width - margin,
        margin + slot_height
    )

    center_x = page_width / 2

    for i in range(0, len(pdf_paths), 2):

        page = output_doc.new_page(
            width=page_width,
            height=page_height
        )

        # Left Bill (Portrait)
        src = fitz.open(pdf_paths[i])

        page.show_pdf_page(
            left_rect,
            src,
            pno=0,
            keep_proportion=True
        )

        src.close()

        # Right Bill (Portrait)
        if i + 1 < len(pdf_paths):

            src = fitz.open(pdf_paths[i + 1])

            page.show_pdf_page(
                right_rect,
                src,
                pno=0,
                keep_proportion=True
            )

            src.close()

        # Cut line
        page.draw_line(
            fitz.Point(center_x, margin),
            fitz.Point(center_x, page_height - margin),
            width=0.7,
            color=(0.5, 0.5, 0.5),
            dashes="[6 6]"
        )

    pdf_bytes = output_doc.tobytes(
        garbage=4,
        deflate=True
    )

    output_doc.close()

    output_pdf = io.BytesIO(pdf_bytes)
    output_pdf.seek(0)

    return output_pdf


def generate_monthly_bills(master_df, ledger_df, selected_month, output_format="WhatsApp PDF"):

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
        master_df[
            [
                "Room No",
                "Name",
                "Bank_Mapping_ID"
            ]
        ],
        on="Room No",
        how="left"
    )
    print(merged_df.columns.tolist())
    merged_df.replace(
        ["NaN", "", None],
        np.nan,
        inplace=True
    )
    print(merged_df.columns.tolist())
    template_path = "assets/Template.docx"

    engine = detect_pdf_engine()

    word_app = None
    generated_pdf_paths = []

    try:

        # ---------------------------------
        # Start MS Word once
        # ---------------------------------
        if engine == "word":

            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()

            word_app = win32com.client.gencache.EnsureDispatch("Word.Application")

            word_app.Visible = False

        # ---------------------------------
        # Temporary folder
        # ---------------------------------
        temp_dir = os.path.abspath("temp_bills")

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        os.makedirs(temp_dir)

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

                generated_pdf_paths.append(pdf_path)

            except Exception as e:

                raise RuntimeError(
                    f"Error generating bill for Room {room_no}\n\n{e}"
                )

        if output_format == "Printable PDF":
            output_pdf = create_printable_pdf(generated_pdf_paths)
        else:
            output_pdf = merge_bill_pdfs(generated_pdf_paths)

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
