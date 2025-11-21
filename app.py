import streamlit as st
import pandas as pd
import io
import csv

# ==========================================
# 🧠 LOGIC & MAPPING
# ==========================================

STORE_MAP = {
    'broadway': '755 (Broadway)',
    '755':      '755 (Broadway)',
    'fulton':   '102 (Fulton St)',
    '102':      '102 (Fulton St)',
    '6th':      '800 (6th Ave)',
    '800':      '800 (6th Ave)',
    '8th':      '901 (8th Ave)',
    '901':      '901 (8th Ave)',
    'maiden':   '100 (Maiden Ln)',
    '100':      '100 (Maiden Ln)'
}

def normalize_store(raw_text):
    if pd.isna(raw_text): return 'Unknown'
    text_lower = str(raw_text).lower()
    for key, standard_name in STORE_MAP.items():
        if key in text_lower:
            return standard_name
    return raw_text

def clean_num(x):
    if isinstance(x, (int, float)): return x
    try:
        clean = str(x).replace(',', '').replace('$', '').replace(' ', '').strip()
        return float(clean) if clean else 0.0
    except: return 0.0

def find_header_row(uploaded_file, target_columns):
    """Scans the uploaded file buffer to find the header row."""
    uploaded_file.seek(0) # Reset pointer to start
    try:
        # decode bytes to string for csv reader
        content = uploaded_file.getvalue().decode('utf-8', errors='replace').splitlines()
        reader = csv.reader(content)
        for i, row in enumerate(reader):
            clean_row = [str(x).strip() for x in row]
            matches = sum(1 for col in target_columns if col in clean_row)
            if matches >= 2:
                uploaded_file.seek(0) # Reset for pandas
                return i
    except Exception as e:
        return None
    return None

# ==========================================
# 🟦 PLATFORM PROCESSORS
# ==========================================

def process_ubereats(uploaded_file):
    target_cols = ['餐厅名称', '销售额（不含税费）', '平台服务费']
    header_row = find_header_row(uploaded_file, target_cols)
    
    if header_row is None: return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    def get_col(col_name):
        return df[col_name].apply(clean_num) if col_name in df.columns else 0.0

    df['Gross_Sales'] = get_col('销售额（不含税费）')
    df['Merchant_Promo'] = get_col('商品优惠（含税）') 
    df['Commission'] = get_col('平台服务费')
    df['Marketing'] = get_col('营销调整额') + get_col('广告支出')
    df['Tax_Adj'] = get_col('销售额税费') + get_col('平台代缴税')
    df['Other_Fees'] = get_col('订单错误调整额') + get_col('派送网络费')
    df['Net_Payout'] = get_col('收入总额')
    
    df['Vendor'] = 'UberEats'
    df['Store_Standard'] = df['餐厅名称'].apply(normalize_store)
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]

def process_doordash(uploaded_file):
    target_cols = ['店铺名称', '小计', '佣金']
    header_row = find_header_row(uploaded_file, target_cols)
    
    if header_row is None: return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    def get_col(col_name):
        matches = [c for c in df.columns if col_name in c]
        if matches:
            return df[matches[0]].apply(clean_num)
        return 0.0

    df['Gross_Sales'] = get_col('小计')
    df['Merchant_Promo'] = get_col('由您出资') 
    df['Commission'] = get_col('佣金')
    df['Marketing'] = get_col('营销费') + get_col('营销积分')
    df['Tax_Adj'] = get_col('税款小计')
    df['Other_Fees'] = get_col('错误费用') + get_col('调整')
    df['Net_Payout'] = get_col('净总计')
    
    df['Vendor'] = 'DoorDash'
    df['Store_Standard'] = df['店铺名称'].apply(normalize_store)
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]

def process_grubhub(uploaded_file):
    target_cols = ['store_name', 'subtotal', 'commission']
    header_row = find_header_row(uploaded_file, target_cols)
    
    if header_row is None: return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    def get_col(col_name):
        return df[col_name].apply(clean_num) if col_name in df.columns else 0.0

    df['Gross_Sales'] = get_col('subtotal')
    df['Merchant_Promo'] = get_col('merchant_funded_promotion') + get_col('merchant_funded_loyalty')
    df['Commission'] = get_col('commission') + get_col('delivery_commission')
    df['Marketing'] = 0.0 
    df['Tax_Adj'] = 0.0 
    df['Other_Fees'] = get_col('processing_fee') + get_col('merchant_service_fee')
    df['Net_Payout'] = get_col('merchant_net_total')
    
    df['Vendor'] = 'Grubhub'
    df['store_info'] = df['store_name'].astype(str) + " " + df.get('street_address', '').astype(str)
    df['Store_Standard'] = df['store_info'].apply(normalize_store)
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]

# ==========================================
# 🖥️ STREAMLIT UI
# ==========================================

st.set_page_config(page_title="3rd Party Reconciliation Tool", layout="wide")

st.title("📊 3rd Party Delivery Financial Reconciliation")
st.markdown("""
This tool consolidates **UberEats, DoorDash, and Grubhub** monthly reports into a single accounting file.
It breaks down fees, commissions, and marketing costs for precise bank reconciliation.
""")

col1, col2, col3 = st.columns(3)

with col1:
    uber_file = st.file_uploader("Upload UberEats CSV", type=['csv'])
with col2:
    dd_file = st.file_uploader("Upload DoorDash CSV", type=['csv'])
with col3:
    gh_file = st.file_uploader("Upload Grubhub CSV", type=['csv'])

if st.button("🚀 Process Files", type="primary"):
    dfs = []
    
    if uber_file:
        df_u = process_ubereats(uber_file)
        if df_u is not None: dfs.append(df_u)
        else: st.error("Error processing Uber file. Check format.")
            
    if dd_file:
        df_d = process_doordash(dd_file)
        if df_d is not None: dfs.append(df_d)
        else: st.error("Error processing DoorDash file. Check format.")

    if gh_file:
        df_g = process_grubhub(gh_file)
        if df_g is not None: dfs.append(df_g)
        else: st.error("Error processing Grubhub file. Check format.")

    if not dfs:
        st.warning("Please upload at least one valid file.")
    else:
        # Processing Logic
        master_df = pd.concat(dfs, ignore_index=True)
        
        summary = master_df.groupby(['Vendor', 'Store_Standard'])[[ 
            'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout'
        ]].sum().reset_index()
        
        summary.insert(4, 'Net_Sales', summary['Gross_Sales'] + summary['Merchant_Promo'])
        
        # Preview in App
        st.subheader("Preview: Fee Breakdown")
        st.dataframe(summary.style.format("${:,.2f}", subset=['Gross_Sales', 'Merchant_Promo', 'Net_Sales', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']))

        # Excel Generation
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            wb = writer.book
            fmt_header = wb.add_format({'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 'border': 1, 'align': 'center', 'text_wrap': True})
            fmt_currency = wb.add_format({'num_format': '$#,##0.00'})
            fmt_currency_red = wb.add_format({'num_format': '$#,##0.00', 'font_color': '#9C0006'})
            fmt_input = wb.add_format({'bg_color': '#FFFFCC', 'border': 1, 'num_format': '$#,##0.00'})
            fmt_bold = wb.add_format({'bold': True, 'border': 1, 'num_format': '$#,##0.00'})

            # Sheet 1: Fee Breakdown
            s1_name = 'Fee_Breakdown'
            summary.to_excel(writer, sheet_name=s1_name, index=False, startrow=1)
            ws1 = writer.sheets[s1_name]
            
            headers1 = ['Vendor', 'Store', 'Gross Sales', 'Merchant Promo', 'Net Sales', 'Commission', 'Marketing', 'Tax Adj', 'Other Fees', 'Net Payout']
            for col, h in enumerate(headers1):
                ws1.write(0, col, h, fmt_header)
            
            ws1.set_column('A:B', 20)
            ws1.set_column('C:J', 15, fmt_currency)
            ws1.set_column('D:D', 15, fmt_currency_red) # Promo
            ws1.set_column('F:I', 15, fmt_currency_red) # Fees

            # Sheet 2: Reconciliation
            s2_name = 'Bank_Reconciliation'
            recon_df = summary[['Vendor', 'Store_Standard', 'Net_Payout']].copy()
            recon_df.to_excel(writer, sheet_name=s2_name, index=False, startrow=1)
            ws2 = writer.sheets[s2_name]
            
            headers2 = ['Vendor', 'Store', 'Calculated Payout', 'Bank Deposit (Fill Me)', 'Hidden Fees (Fill Me)', 'Variance']
            for col, h in enumerate(headers2):
                ws2.write(0, col, h, fmt_header)

            ws2.set_column('A:B', 20)
            ws2.set_column('C:C', 18, fmt_currency)
            ws2.set_column('D:E', 18, fmt_input)
            ws2.set_column('F:F', 18, fmt_bold)

            for i in range(2, len(recon_df) + 2):
                ws2.write_formula(f'F{i}', f'=C{i}-D{i}+E{i}', fmt_bold)
                
        output.seek(0)
        
        st.success("Processing Complete!")
        st.download_button(
            label="📥 Download Excel Reconciliation Report",
            data=output,
            file_name="Financial_Reconciliation_Report.xlsx",
            mime="application/vnd.ms-excel"
        )