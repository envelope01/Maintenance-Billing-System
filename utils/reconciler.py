import pdfplumber
import pandas as pd
import numpy as np

def extract_bank_statement(pdf_file):
    all_rows = []
    
    # 1. Extract tables using your logic
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table_data = page.extract_table()
            if table_data:
                all_rows.extend(table_data)

    # 2. Convert to DataFrame
    df = pd.DataFrame(all_rows)

    # 3. Promote header
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)

    # 4. Filter duplicate headers
    df = df[df.iloc[:, 0] != df.columns[0]].reset_index(drop=True)
    
    # ----------------------------------------------------
    # DATA CLEANING: Strict column formatting
    # ----------------------------------------------------
    # Remove extra spaces from column names
    df.columns = df.columns.str.strip()
    
    # Keep only necessary columns (avoiding KeyErrors if extra spaces exist)
    target_cols = ['Value Date', 'Description', 'Credit']
    available_cols = [c for c in df.columns if c in target_cols]
    df = df[available_cols].copy()

    # Clean Credit column: Remove commas, convert to numeric, replace blank/nan with 0
    df['Credit'] = df['Credit'].astype(str).str.replace(',', '', regex=False)
    df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0)

    # Filter out rows where Credit is 0 (we only care about money received)
    valid_payments = df[df['Credit'] > 0].copy()
    
    return valid_payments



def map_bank_to_rooms(raw_bank_df, mapping_sheet_df):
    # 1. Smart Column Detection (Taki Exact spelling ka lafda na rahe)
    mapping_sheet_df.columns = mapping_sheet_df.columns.astype(str).str.strip().str.lower()
    
    t_col = [c for c in mapping_sheet_df.columns if 'transaction' in c][0]
    r_col = [c for c in mapping_sheet_df.columns if 'room' in c][0]
    
    mapping_dict = {}
    for _, row in mapping_sheet_df.iterrows():
        t_val = row[t_col]
        r_val = row[r_col]
        
        # Skip empty rows
        if pd.isna(t_val) or str(t_val).strip() == '':
            continue
            
        # FIX THE ".0" TRAP FOR TRANSACTION IDs
        if isinstance(t_val, float) and t_val.is_integer():
            t_str = str(int(t_val)).upper().strip()
        else:
            t_str = str(t_val).upper().strip()
            
        # FIX ROOM NO DATA TYPES (Ensure it's a clean string)
        if isinstance(r_val, float) and r_val.is_integer():
            r_str = str(int(r_val)).strip()
        else:
            r_str = str(r_val).strip()
            
        mapping_dict[t_str] = r_str

    # 2. Find the match
    def find_room(description):
        desc = str(description).upper()
        for t_id, room in mapping_dict.items():
            if t_id in desc:
                return room
        return np.nan # Strictly using np.nan for missing matches

    raw_bank_df['Mapped_Room_No'] = raw_bank_df['Description'].apply(find_room)
    
    mapped_df = raw_bank_df.dropna(subset=['Mapped_Room_No']).copy()
    unmapped_df = raw_bank_df[raw_bank_df['Mapped_Room_No'].isna()].copy()
    
    grouped_payments = mapped_df.groupby('Mapped_Room_No')['Credit'].sum().reset_index()
    grouped_payments.rename(columns={'Mapped_Room_No': 'Room No', 'Credit': 'Total_Paid'}, inplace=True)
    
    return grouped_payments, unmapped_df


def generate_reconciliation_report(grouped_payments, dues_df):
    dues_df.columns = dues_df.columns.str.strip()
    
    # Ensure Room No in dues_df is EXACTLY the same format (clean string) as grouped_payments
    def clean_room_no(val):
        if pd.isna(val) or val is np.nan:
            return np.nan
        if isinstance(val, float) and val.is_integer():
            return str(int(val)).strip()
        return str(val).strip()
        
    dues_df['Room No'] = dues_df['Room No'].apply(clean_room_no)
    grouped_payments['Room No'] = grouped_payments['Room No'].apply(clean_room_no)
    
    dues_df['Total Dues'] = pd.to_numeric(dues_df['Total Dues'], errors='coerce').fillna(0)
    
    report_df = pd.merge(
        dues_df[['Room No', 'Name', 'Total Dues']], 
        grouped_payments, 
        on='Room No', 
        how='left'
    )
    
    report_df['Total_Paid'] = report_df['Total_Paid'].fillna(0)
    
    def get_status(row):
        if row['Total_Paid'] >= (row['Total Dues'] - 1):
            return "Fully Paid"
        elif row['Total_Paid'] > 0:
            return "Partially Paid"
        else:
            return "Unpaid"
            
    report_df['Status'] = report_df.apply(get_status, axis=1)
    return report_df