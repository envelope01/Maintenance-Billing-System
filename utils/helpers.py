import calendar
import re

import numpy as np
import pandas as pd
import pdfplumber

def get_billing_dates(selected_month):
    ts = pd.Timestamp(selected_month)
    last_day = calendar.monthrange(ts.year, ts.month)[1]

    return {
        "Bill_Month": ts.strftime("%B %Y"),
        "Bill_Date": ts.strftime("%d %B %Y"),
        "Billing_From": ts.strftime("%d/%m/%Y"),
        "Billing_To": ts.replace(day=last_day).strftime("%d/%m/%Y"),
        "Due_Date": ts.replace(day=25).strftime("%d %B %Y")
    }

def format_amount(value):
    if pd.isna(value) or value is np.nan or value == "":
        return "0" 
        
    try:
        clean_val = int(round(float(value)))
        return str(clean_val)
    except (ValueError, TypeError):
        return str(value)
    
def get_statement_month(pdf_file):
    """
    Extract statement month from the first page
    and return it in the same format as testData.

    Example:
    01/05/2026 To 31/05/2026
            ↓
    01-05-2026
    """

    pdf_file.seek(0)

    with pdfplumber.open(pdf_file) as pdf:

        first_page = pdf.pages[0].extract_text() or ""

    match = re.search(
        r'(\d{2}/\d{2}/\d{4})\s+To\s+\d{2}/\d{2}/\d{4}',
        first_page,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            "Unable to detect Statement Month."
        )

    first_date = pd.to_datetime(
        match.group(1),
        dayfirst=True
    )

    return first_date.strftime("%d-%m-%Y")