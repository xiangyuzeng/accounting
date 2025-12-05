import streamlit as st
import pandas as pd
import io
import csv

# ==========================================
# 🎨 页面配置与 CSS 样式 (Luckin 风格)
# ==========================================
st.set_page_config(page_title="瑞幸咖啡财务对账系统", layout="wide", page_icon="☕")

luckin_blue = "#0022AB"

st.markdown(f"""
    <style>
    .main {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
    .stButton>button {{
        background-color: {luckin_blue}; color: white; border-radius: 5px;
        height: 3em; width: 100%; font-weight: bold; border: none;
    }}
    .stButton>button:hover {{ background-color: #00187A; color: white; }}
    h1, h2, h3 {{ color: #333333; }}
    .stAlert {{ background-color: #EEF4FF; border-left: 5px solid {luckin_blue}; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🧠 核心逻辑 & 映射
# ==========================================

# 官方门店ID映射
STORE_ID_MAP = {
    'US00001': 'US00001 - Broadway (755)',
    'US00002': 'US00002 - 6th Ave (800)',
    'US00003': 'US00003 - Maiden Lane (100)',
    'US00004': 'US00004 - 37th St',
    'US00005': 'US00005 - 8th Ave (901)',
    'US00006': 'US00006 - Fulton St (102)',
}

# Uber location name mapping
UBER_LOCATION_MAP = {
    'broadway': 'US00001',
    '6th ave': 'US00002',
    'sixth ave': 'US00002',
    'maiden': 'US00003',
    '37th': 'US00004',
    '8th ave': 'US00005',
    'eighth ave': 'US00005',
    'fulton': 'US00006',
}

def extract_store_id(raw_text, platform='generic'):
    """Extract standardized store ID from various platform formats"""
    if pd.isna(raw_text):
        return '未知门店'
    
    text = str(raw_text).strip()
    text_lower = text.lower()
    
    # Check for direct US000XX pattern
    import re
    match = re.search(r'US0000[1-6]', text, re.IGNORECASE)
    if match:
        store_id = match.group().upper()
        return STORE_ID_MAP.get(store_id, store_id)
    
    # Platform-specific mapping
    if platform == 'uber':
        for key, store_id in UBER_LOCATION_MAP.items():
            if key in text_lower:
                return STORE_ID_MAP.get(store_id, store_id)
    
    # Address-based mapping for Grubhub
    address_map = {
        '755': 'US00001', 'broadway': 'US00001',
        '800': 'US00002', '6th': 'US00002',
        '100': 'US00003', 'maiden': 'US00003',
        '37': 'US00004',
        '901': 'US00005', '8th': 'US00005',
        '102': 'US00006', 'fulton': 'US00006',
    }
    
    for key, store_id in address_map.items():
        if key in text_lower:
            return STORE_ID_MAP.get(store_id, store_id)
    
    return text[:30] if len(text) > 30 else text

def clean_num(x):
    """Convert various number formats to float"""
    if isinstance(x, (int, float)):
        return x
    try:
        clean = str(x).replace(',', '').replace('$', '').replace(' ', '').strip()
        return float(clean) if clean else 0.0
    except:
        return 0.0

def find_header_row(uploaded_file, target_columns):
    """Find the row containing column headers"""
    uploaded_file.seek(0)
    try:
        content = uploaded_file.getvalue().decode('utf-8', errors='replace').splitlines()
        reader = csv.reader(content)
        for i, row in enumerate(reader):
            clean_row = [str(x).strip() for x in row]
            matches = sum(1 for col in target_columns if col in clean_row)
            if matches >= 2:
                uploaded_file.seek(0)
                return i
    except Exception:
        return None
    return None

# ==========================================
# 🟦 平台数据处理 - 修正版（费用转正数）
# ==========================================

def process_ubereats(uploaded_file):
    """Process UberEats CSV - fees converted to positive values"""
    target_cols = ['餐厅名称', '销售额（不含税费）', '平台服务费']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    # Date filter - October 2025 only
    if '订单日期' in df.columns:
        df['Date'] = pd.to_datetime(df['订单日期'], format='%m/%d/%Y', errors='coerce')
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
    
    def get_col(col_name):
        return df[col_name].apply(clean_num) if col_name in df.columns else pd.Series([0.0] * len(df))

    # 收入项（正数）
    df['Gross_Sales'] = get_col('销售额（不含税费）')
    df['Tax_Collected'] = get_col('销售额税费')
    
    # 费用项（原始负数 → 取绝对值）
    df['Discount'] = get_col('商品优惠（含税）').abs()  # 折扣支出
    df['Commission'] = get_col('平台服务费').abs()  # 平台佣金
    df['Order_Error'] = get_col('订单错误调整额').abs()  # 订单错误
    
    # 补贴/返还（正数收入）
    df['Marketing_Credit'] = get_col('营销调整额')  # Uber给的营销补贴
    
    # 净入账 = 使用column 26 (调整后的总销售额含税费) 与 Analytics 保持一致
    # 但这里我们重新计算以便理解
    df['Calculated_Net'] = (df['Gross_Sales'] + df['Tax_Collected'] 
                           - df['Discount'] - df['Commission'] 
                           - df['Order_Error'] + df['Marketing_Credit'])
    
    # 实际净入账（来自CSV）
    df['Net_Payout'] = get_col('收入总额')
    
    df['Vendor'] = 'UberEats'
    df['Store_Standard'] = df['餐厅名称'].apply(lambda x: extract_store_id(x, 'uber'))
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Tax_Collected', 
               'Discount', 'Commission', 'Marketing_Credit', 'Order_Error', 
               'Calculated_Net', 'Net_Payout']]

def process_doordash(uploaded_file):
    """Process DoorDash CSV - fees converted to positive values"""
    target_cols = ['店铺名称', '小计', '佣金']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    # Date filter - October 2025 only
    if '时间戳本地日期' in df.columns:
        df['Date'] = pd.to_datetime(df['时间戳本地日期'], format='%m/%d/%Y', errors='coerce')
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
    
    def get_col(col_name):
        matches = [c for c in df.columns if col_name in c]
        if matches:
            return df[matches[0]].apply(clean_num)
        return pd.Series([0.0] * len(df))

    # 收入项
    df['Gross_Sales'] = get_col('小计')
    df['Tax_Collected'] = get_col('税款小计')
    
    # 费用项（取绝对值）
    df['Discount'] = get_col('由您出资').abs()  # 商家承担的折扣
    df['Commission'] = get_col('佣金').abs()  # 佣金
    df['Marketing_Fee'] = get_col('营销费').abs()  # 营销费
    df['Order_Error'] = get_col('错误费用').abs()
    
    # 补贴/返还
    df['Marketing_Credit'] = get_col('营销积分')  # DoorDash给的积分
    df['DD_Funded'] = get_col('由 DoorDash 出资').abs()  # DD承担的折扣（对商家是好事）
    
    # 合并费用类
    df['Total_Discount'] = df['Discount']
    df['Total_Commission'] = df['Commission']
    df['Total_Marketing'] = df['Marketing_Fee']
    df['Total_Credit'] = df['Marketing_Credit'] + df['DD_Funded']
    
    # 净入账
    df['Net_Payout'] = get_col('净总计')
    
    df['Vendor'] = 'DoorDash'
    df['Store_Standard'] = df['店铺名称'].apply(lambda x: extract_store_id(x, 'doordash'))
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Tax_Collected',
               'Total_Discount', 'Total_Commission', 'Total_Marketing', 
               'Total_Credit', 'Order_Error', 'Net_Payout']]

def process_grubhub(uploaded_file):
    """Process Grubhub CSV - fees converted to positive values"""
    target_cols = ['store_name', 'subtotal', 'commission']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    # Date filter - October 2025 only (exclude records with invalid dates)
    if 'transaction_date' in df.columns:
        df['Date'] = pd.to_datetime(df['transaction_date'], format='%m/%d/%Y', errors='coerce')
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
    
    def get_col(col_name):
        return df[col_name].apply(clean_num) if col_name in df.columns else pd.Series([0.0] * len(df))

    # 收入项
    df['Gross_Sales'] = get_col('subtotal')
    df['Tax_Collected'] = get_col('subtotal_sales_tax')
    
    # 费用项（取绝对值）
    df['Commission'] = get_col('commission').abs()
    df['Delivery_Commission'] = get_col('delivery_commission').abs()
    df['Processing_Fee'] = get_col('processing_fee').abs()
    df['Merchant_Promo'] = get_col('merchant_funded_promotion').abs()
    df['Merchant_Loyalty'] = get_col('merchant_funded_loyalty').abs()
    
    # 合并
    df['Total_Discount'] = df['Merchant_Promo'] + df['Merchant_Loyalty']
    df['Total_Commission'] = df['Commission'] + df['Delivery_Commission']
    df['Total_Processing'] = df['Processing_Fee']
    
    # 净入账
    df['Net_Payout'] = get_col('merchant_net_total')
    
    df['Vendor'] = 'Grubhub'
    # Use street_address for store identification
    store_info = df['store_name'].astype(str) + " " + df.get('street_address', pd.Series(['']*len(df))).astype(str)
    df['Store_Standard'] = store_info.apply(lambda x: extract_store_id(x, 'grubhub'))
    
    return df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Tax_Collected',
               'Total_Discount', 'Total_Commission', 'Total_Processing', 'Net_Payout']]

# ==========================================
# 🖥️ STREAMLIT UI
# ==========================================

# Logo loading - use relative path for Streamlit Cloud deployment
import os
logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
if os.path.exists(logo_path):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(logo_path, width=120)
    with col_title:
        st.markdown(f"<h1 style='color:{luckin_blue}; margin-top: 20px;'>luckin coffee</h1>", unsafe_allow_html=True)
        st.markdown("## 财务对账自动化平台 v4.0")
else:
    st.markdown(f"<h1 style='color:{luckin_blue};'>☕ luckin coffee</h1>", unsafe_allow_html=True)
    st.markdown("## 财务对账自动化平台 v4.0")
st.markdown("### 费用明细分析 (Fee Breakdown Analysis)")
st.markdown("---")

# 侧边栏说明
with st.sidebar:
    st.header("📘 使用说明")
    st.info("""
    **Version 4.0 更新:**
    - ✅ 费用显示为正数（支出）
    - ✅ 清晰区分各类费用
    - ✅ 与 Analytics App 数据对齐
    - ✅ 仅统计10月数据
    """)
    
    st.markdown("### 💡 数据说明")
    st.markdown("""
    **CSV原始数据规则:**
    - 负数 = 平台扣款（费用）
    - 正数 = 收入或补贴
    
    **本报表显示规则:**
    - 费用全部显示为**正数**
    - 方便会计理解和入账
    """)

# 上传区域
st.subheader("📂 请上传平台账单 (CSV)")
col1, col2, col3 = st.columns(3)

with col1:
    uber_file = st.file_uploader("UberEats 账单", type=['csv'])
with col2:
    dd_file = st.file_uploader("DoorDash 账单", type=['csv'])
with col3:
    gh_file = st.file_uploader("Grubhub 账单", type=['csv'])

st.markdown("<br>", unsafe_allow_html=True)

if st.button("🚀 开始自动化对账处理", type="primary"):
    results = {'UberEats': None, 'DoorDash': None, 'Grubhub': None}
    
    my_bar = st.progress(0)
    
    if uber_file:
        results['UberEats'] = process_ubereats(uber_file)
        if results['UberEats'] is None:
            st.error("❌ UberEats 文件格式错误")
    my_bar.progress(30)
    
    if dd_file:
        results['DoorDash'] = process_doordash(dd_file)
        if results['DoorDash'] is None:
            st.error("❌ DoorDash 文件格式错误")
    my_bar.progress(60)
    
    if gh_file:
        results['Grubhub'] = process_grubhub(gh_file)
        if results['Grubhub'] is None:
            st.error("❌ Grubhub 文件格式错误")
    my_bar.progress(90)
    
    if all(v is None for v in results.values()):
        st.warning("⚠️ 请至少上传一个有效的 CSV 文件。")
        my_bar.empty()
    else:
        my_bar.progress(100)
        st.success("✅ 数据处理完成！")
        
        # ==========================================
        # 📊 分平台详细报告
        # ==========================================
        
        for platform, df in results.items():
            if df is not None and len(df) > 0:
                st.markdown(f"---")
                st.subheader(f"📊 {platform} 费用明细")
                
                # 汇总统计
                summary_data = {
                    '订单数': len(df),
                    '销售额 (Gross)': df['Gross_Sales'].sum(),
                    '税费收入': df['Tax_Collected'].sum(),
                }
                
                if platform == 'UberEats':
                    summary_data.update({
                        '💸 折扣支出': df['Discount'].sum(),
                        '💸 平台佣金': df['Commission'].sum(),
                        '💰 营销补贴 (收入)': df['Marketing_Credit'].sum(),
                        '💸 订单错误': df['Order_Error'].sum(),
                        '净入账': df['Net_Payout'].sum(),
                    })
                    
                elif platform == 'DoorDash':
                    summary_data.update({
                        '💸 折扣支出 (商家)': df['Total_Discount'].sum(),
                        '💸 平台佣金': df['Total_Commission'].sum(),
                        '💸 营销费': df['Total_Marketing'].sum(),
                        '💰 平台补贴 (收入)': df['Total_Credit'].sum(),
                        '净入账': df['Net_Payout'].sum(),
                    })
                    
                elif platform == 'Grubhub':
                    summary_data.update({
                        '💸 折扣支出': df['Total_Discount'].sum(),
                        '💸 佣金合计': df['Total_Commission'].sum(),
                        '💸 处理费': df['Total_Processing'].sum(),
                        '净入账': df['Net_Payout'].sum(),
                    })
                
                # 显示汇总卡片
                cols = st.columns(4)
                for i, (key, val) in enumerate(summary_data.items()):
                    with cols[i % 4]:
                        if isinstance(val, (int, float)):
                            if '订单' in key:
                                st.metric(key, f"{int(val):,}")
                            elif '💸' in key:
                                st.metric(key, f"${val:,.2f}", delta=None)
                            elif '💰' in key:
                                st.metric(key, f"${val:,.2f}", delta="补贴")
                            else:
                                st.metric(key, f"${val:,.2f}")
        
        # ==========================================
        # 📊 三平台汇总
        # ==========================================
        st.markdown("---")
        st.subheader("📊 三平台费用汇总")
        
        total_orders = sum(len(df) for df in results.values() if df is not None)
        total_gross = sum(df['Gross_Sales'].sum() for df in results.values() if df is not None)
        total_net = sum(df['Net_Payout'].sum() for df in results.values() if df is not None)
        
        # 计算各类费用总和
        total_discount = 0
        total_commission = 0
        total_marketing = 0
        total_processing = 0
        total_credit = 0
        
        if results['UberEats'] is not None:
            df = results['UberEats']
            total_discount += df['Discount'].sum()
            total_commission += df['Commission'].sum()
            total_credit += df['Marketing_Credit'].sum()
        
        if results['DoorDash'] is not None:
            df = results['DoorDash']
            total_discount += df['Total_Discount'].sum()
            total_commission += df['Total_Commission'].sum()
            total_marketing += df['Total_Marketing'].sum()
            total_credit += df['Total_Credit'].sum()
        
        if results['Grubhub'] is not None:
            df = results['Grubhub']
            total_discount += df['Total_Discount'].sum()
            total_commission += df['Total_Commission'].sum()
            total_processing += df['Total_Processing'].sum()
        
        st.markdown(f"""
        ### 📈 费用汇总表 (10月)
        
        | 项目 | 金额 | 说明 |
        |------|------|------|
        | **总订单数** | {total_orders:,} | 三平台合计 |
        | **销售总额** | ${total_gross:,.2f} | Gross Sales (不含税) |
        | **💸 折扣/促销** | ${total_discount:,.2f} | 商家承担的促销成本 |
        | **💸 平台佣金** | ${total_commission:,.2f} | 各平台服务费 |
        | **💸 营销费** | ${total_marketing:,.2f} | 广告/推广费用 |
        | **💸 处理费** | ${total_processing:,.2f} | 支付处理费 |
        | **💰 平台补贴** | ${total_credit:,.2f} | 平台给的营销返还 |
        | **费用净额** | ${(total_discount + total_commission + total_marketing + total_processing - total_credit):,.2f} | 扣除补贴后的实际费用 |
        | **净入账** | ${total_net:,.2f} | 实际收到金额 |
        """)
        
        # 费率分析
        if total_gross > 0:
            st.markdown("### 📊 费率分析")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("折扣率", f"{(total_discount/total_gross)*100:.1f}%")
            with col2:
                st.metric("佣金率", f"{(total_commission/total_gross)*100:.1f}%")
            with col3:
                st.metric("营销费率", f"{(total_marketing/total_gross)*100:.1f}%")
            with col4:
                net_rate = (total_net / total_gross) * 100
                st.metric("净收入率", f"{net_rate:.1f}%")
        
        # ==========================================
        # 📥 Excel 导出
        # ==========================================
        st.markdown("---")
        st.subheader("📥 导出报表")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            wb = writer.book
            
            # 格式定义
            fmt_header = wb.add_format({
                'bold': True, 'bg_color': '#0022AB', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter'
            })
            fmt_currency = wb.add_format({'num_format': '$#,##0.00'})
            fmt_expense = wb.add_format({'num_format': '$#,##0.00', 'font_color': '#C00000'})
            fmt_income = wb.add_format({'num_format': '$#,##0.00', 'font_color': '#008000'})
            
            # Sheet 1: 费用汇总
            summary_rows = [
                ['项目', 'UberEats', 'DoorDash', 'Grubhub', '合计'],
                ['订单数', 
                 len(results['UberEats']) if results['UberEats'] is not None else 0,
                 len(results['DoorDash']) if results['DoorDash'] is not None else 0,
                 len(results['Grubhub']) if results['Grubhub'] is not None else 0,
                 total_orders],
                ['销售总额',
                 results['UberEats']['Gross_Sales'].sum() if results['UberEats'] is not None else 0,
                 results['DoorDash']['Gross_Sales'].sum() if results['DoorDash'] is not None else 0,
                 results['Grubhub']['Gross_Sales'].sum() if results['Grubhub'] is not None else 0,
                 total_gross],
            ]
            
            # Add fee breakdowns
            uber_discount = results['UberEats']['Discount'].sum() if results['UberEats'] is not None else 0
            dd_discount = results['DoorDash']['Total_Discount'].sum() if results['DoorDash'] is not None else 0
            gh_discount = results['Grubhub']['Total_Discount'].sum() if results['Grubhub'] is not None else 0
            
            uber_comm = results['UberEats']['Commission'].sum() if results['UberEats'] is not None else 0
            dd_comm = results['DoorDash']['Total_Commission'].sum() if results['DoorDash'] is not None else 0
            gh_comm = results['Grubhub']['Total_Commission'].sum() if results['Grubhub'] is not None else 0
            
            dd_mkt = results['DoorDash']['Total_Marketing'].sum() if results['DoorDash'] is not None else 0
            gh_proc = results['Grubhub']['Total_Processing'].sum() if results['Grubhub'] is not None else 0
            
            uber_credit = results['UberEats']['Marketing_Credit'].sum() if results['UberEats'] is not None else 0
            dd_credit = results['DoorDash']['Total_Credit'].sum() if results['DoorDash'] is not None else 0
            
            uber_net = results['UberEats']['Net_Payout'].sum() if results['UberEats'] is not None else 0
            dd_net = results['DoorDash']['Net_Payout'].sum() if results['DoorDash'] is not None else 0
            gh_net = results['Grubhub']['Net_Payout'].sum() if results['Grubhub'] is not None else 0
            
            summary_rows.extend([
                ['折扣/促销 (支出)', uber_discount, dd_discount, gh_discount, total_discount],
                ['平台佣金 (支出)', uber_comm, dd_comm, gh_comm, total_commission],
                ['营销费 (支出)', 0, dd_mkt, 0, total_marketing],
                ['处理费 (支出)', 0, 0, gh_proc, total_processing],
                ['平台补贴 (收入)', uber_credit, dd_credit, 0, total_credit],
                ['净入账', uber_net, dd_net, gh_net, total_net],
            ])
            
            summary_df = pd.DataFrame(summary_rows[1:], columns=summary_rows[0])
            summary_df.to_excel(writer, sheet_name='费用汇总', index=False, startrow=1)
            
            ws1 = writer.sheets['费用汇总']
            for col, h in enumerate(summary_rows[0]):
                ws1.write(0, col, h, fmt_header)
            ws1.set_column('A:A', 20)
            ws1.set_column('B:E', 15, fmt_currency)
            
            # Sheet 2: 各平台明细
            for platform, df in results.items():
                if df is not None:
                    df.to_excel(writer, sheet_name=f'{platform}明细', index=False)
        
        output.seek(0)
        
        st.download_button(
            label="📥 下载 Excel 对账报表",
            data=output,
            file_name="Luckin_Fee_Breakdown_Report_v4.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.info("""
        **报表说明:**
        - 💸 标记的费用项显示为**正数**（代表支出）
        - 💰 标记的补贴项显示为**正数**（代表收入）
        - 净入账 = CSV中平台报告的实际入账金额
        """)
