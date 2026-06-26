import pandas as pd

from docxtpl import DocxTemplate

from utils.config import (
    REQUIRED_COLUMNS,
    MAPPING
)

def validate_excel(df):

    missing = [
        col
        for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing Excel Columns:\n"
            + "\n".join(missing)
        )


def validate_template(template_path):
    doc = DocxTemplate(template_path)
    variables = (
        doc.get_undeclared_template_variables()
    )

    expected = set(MAPPING.values())

    expected.update({
        "Bill_Date",
        "Due_Date",
        "Billing_From",
        "Billing_To",
        "Bill_Month"
    })

    missing = expected - variables

    extra = variables - expected

    if missing:
        raise ValueError(
            "Missing placeholders:\n"
            + "\n".join(sorted(missing))
        )

    if extra:
        raise ValueError(
            "Unknown placeholders:\n"
            + "\n".join(sorted(extra))
        )