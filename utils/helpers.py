import calendar
import pandas as pd
import numpy as np

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
    except ValueError:
        return str(value)