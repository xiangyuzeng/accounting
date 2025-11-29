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
    .main {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }}
    .stButton>button {{
        background-color: {luckin_blue};
        color: white;
        border-radius: 5px;
        height: 3em;
        width: 100%;
        font-weight: bold;
        border: none;
    }}
    .stButton>button:hover {{
        background-color: #00187A;
        color: white;
    }}
    h1, h2, h3 {{
        color: #333333;
    }}
    .stAlert {{
        background-color: #EEF4FF;
        border-left: 5px solid {luckin_blue};
    }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🧠 核心逻辑 & 门店映射
# ==========================================

# 标准门店ID映射 (官方定义)
STORE_ID_DISPLAY = {
    'US00001': 'US00001 - Broadway (百老汇店)',
    'US00002': 'US00002 - 6th Ave (第六大道店)',
    'US00003': 'US00003 - Maiden Lane (梅登巷店)',
    'US00004': 'US00004 - 37th St (37街店)',
    'US00005': 'US00005 - 8th Ave (第八大道店)',
    'US00006': 'US00006 - Fulton St (富尔顿街店)'
}

def normalize_store_doordash(raw_text):
    """DoorDash: 从店铺名称中提取门店ID (如 'Luckin Coffee US00002' -> 'US00001')"""
    if pd.isna(raw_text):
        return '未知门店'
    text = str(raw_text).upper().replace(' ', '')
    
    # 匹配 US00001-US00006
    for store_id in STORE_ID_DISPLAY.keys():
        if store_id.replace(' ', '') in text:
            return STORE_ID_DISPLAY[store_id]
    
    return str(raw_text)

def normalize_store_uber(raw_text):
    """Uber: 从餐厅名称中提取门店 (如 'Luckin Coffee (Broadway)' -> 'US00001')"""
    if pd.isna(raw_text):
        return '未知门店'
    text_lower = str(raw_text).lower()
    
    # Uber 门店名称映射到标准ID
    if 'broadway' in text_lower:
        return STORE_ID_DISPLAY['US00001']
    elif '6th' in text_lower:
        return STORE_ID_DISPLAY['US00002']
    elif 'maiden' in text_lower:
        return STORE_ID_DISPLAY['US00003']
    elif '37th' in text_lower:
        return STORE_ID_DISPLAY['US00004']
    elif '8th' in text_lower:
        return STORE_ID_DISPLAY['US00005']
    elif 'fulton' in text_lower:
        return STORE_ID_DISPLAY['US00006']
    
    return str(raw_text)

def normalize_store_grubhub(store_number, street_address):
    """Grubhub: 优先使用地址判断门店 (因为Grubhub的store_number不一致)"""
    address = str(street_address).lower() if not pd.isna(street_address) else ''
    
    # 根据实际地址映射到标准门店ID
    if '755' in address or 'broadway' in address:
        return STORE_ID_DISPLAY['US00001']
    elif '800' in address or '6th' in address:
        return STORE_ID_DISPLAY['US00002']
    elif '100' in address or 'maiden' in address:
        return STORE_ID_DISPLAY['US00003']
    elif '37th' in address:
        return STORE_ID_DISPLAY['US00004']
    elif '901' in address or '8th' in address:
        return STORE_ID_DISPLAY['US00005']
    elif '102' in address or 'fulton' in address:
        return STORE_ID_DISPLAY['US00006']
    
    # 如果地址无法识别，尝试用store_number
    store_num = str(store_number).upper().replace(' ', '') if not pd.isna(store_number) else ''
    for store_id in STORE_ID_DISPLAY.keys():
        if store_id in store_num:
            return STORE_ID_DISPLAY[store_id]
    
    return f'未知门店 ({store_number})'

def clean_num(x):
    """清洗数字字段"""
    if isinstance(x, (int, float)):
        return x
    try:
        clean = str(x).replace(',', '').replace('$', '').replace(' ', '').strip()
        return float(clean) if clean else 0.0
    except:
        return 0.0

def find_header_row(uploaded_file, target_columns):
    """查找CSV表头行"""
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
# 🟦 平台数据处理
# ==========================================

def process_ubereats(uploaded_file):
    """处理 UberEats 数据"""
    target_cols = ['餐厅名称', '销售额（不含税费）', '平台服务费']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None, "未找到有效表头"

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
    df['Store_Standard'] = df['餐厅名称'].apply(normalize_store_uber)
    
    result = df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]
    return result, f"✅ UberEats: 成功处理 {len(result)} 条记录"

def process_doordash(uploaded_file):
    """处理 DoorDash 数据"""
    target_cols = ['店铺名称', '小计', '佣金']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None, "未找到有效表头"

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
    df['Store_Standard'] = df['店铺名称'].apply(normalize_store_doordash)
    
    result = df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]
    return result, f"✅ DoorDash: 成功处理 {len(result)} 条记录"

def process_grubhub(uploaded_file):
    """处理 Grubhub 数据 (含日期修复逻辑)"""
    target_cols = ['store_name', 'subtotal', 'commission']
    header_row = find_header_row(uploaded_file, target_cols)
    if header_row is None:
        return None, "未找到有效表头"

    df = pd.read_csv(uploaded_file, header=header_row)
    df.columns = df.columns.str.strip()
    
    def get_col(col_name):
        return df[col_name].apply(clean_num) if col_name in df.columns else 0.0

    # 处理日期 (与分析系统保持一致的逻辑)
    warning_msg = ""
    if 'transaction_date' in df.columns:
        df['Date'] = pd.to_datetime(df['transaction_date'], format='%m/%d/%Y', errors='coerce')
        if df['Date'].isna().all():
            warning_msg = " ⚠️ 日期数据异常，已按记录顺序处理"

    df['Gross_Sales'] = get_col('subtotal')
    df['Merchant_Promo'] = get_col('merchant_funded_promotion') + get_col('merchant_funded_loyalty')
    df['Commission'] = get_col('commission') + get_col('delivery_commission')
    df['Marketing'] = 0.0 
    df['Tax_Adj'] = get_col('subtotal_sales_tax')
    df['Other_Fees'] = get_col('processing_fee') + get_col('merchant_service_fee') + get_col('gh_plus_commission')
    df['Net_Payout'] = get_col('merchant_net_total')
    
    df['Vendor'] = 'Grubhub'
    
    # 使用地址优先的门店标准化
    df['Store_Standard'] = df.apply(
        lambda row: normalize_store_grubhub(
            row.get('store_number', ''), 
            row.get('street_address', '')
        ), axis=1
    )
    
    result = df[['Vendor', 'Store_Standard', 'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout']]
    return result, f"✅ Grubhub: 成功处理 {len(result)} 条记录{warning_msg}"

# ==========================================
# 🖥️ STREAMLIT UI
# ==========================================

# --- Logo & Header ---
st.markdown(f"<h1 style='color:{luckin_blue};'>☕ luckin coffee</h1>", unsafe_allow_html=True)
st.markdown("## 财务对账自动化平台 (Financial Reconciliation)")
st.markdown("---")

# --- 侧边栏：说明文档 ---
with st.sidebar:
    st.header("📘 使用说明")
    st.info("""
    **第一步：** 上传 UberEats, DoorDash, Grubhub 的月度 CSV 账单。
    
    **第二步：** 系统会自动清洗数据、统一店铺名称、并按财务科目拆解费用。
    
    **第三步：** 下载 Excel 对账单，进行差异调节。
    """)
    
    st.markdown("### 💡 计算逻辑说明")
    st.markdown("""
    *   **销售总额**: 订单原本金额 (Gross Sales)
    *   **商家折扣**: 由我们承担的促销成本 (Promo)
    *   **净销售额**: 销售总额 + 商家折扣 (实际收入基础)
    *   **计算净入账**: 净销售额 - 佣金 - 营销费 - 税金调整 - 其他费用
    """)
    
    st.markdown("---")
    st.markdown("### 🏪 门店ID映射")
    st.markdown("""
    | ID | 门店名称 |
    |---|---|
    | US00001 | Broadway (百老汇店) |
    | US00002 | 6th Ave (第六大道店) |
    | US00003 | Maiden Lane (梅登巷店) |
    | US00004 | 37th St (37街店) |
    | US00005 | 8th Ave (第八大道店) |
    | US00006 | Fulton St (富尔顿街店) |
    """)

# --- 上传区域 ---
st.subheader("📂 请上传平台账单 (CSV)")
col1, col2, col3 = st.columns(3)

with col1:
    uber_file = st.file_uploader("UberEats 账单", type=['csv'])
with col2:
    dd_file = st.file_uploader("DoorDash 账单", type=['csv'])
with col3:
    gh_file = st.file_uploader("Grubhub 账单", type=['csv'])

# --- 处理按钮 ---
st.markdown("<br>", unsafe_allow_html=True)
if st.button("🚀 开始自动化对账处理", type="primary"):
    dfs = []
    messages = []
    
    my_bar = st.progress(0)
    
    if uber_file:
        df_u, msg = process_ubereats(uber_file)
        if df_u is not None:
            dfs.append(df_u)
            messages.append(msg)
        else:
            st.error(f"❌ UberEats 文件格式错误: {msg}")
    my_bar.progress(30)
            
    if dd_file:
        df_d, msg = process_doordash(dd_file)
        if df_d is not None:
            dfs.append(df_d)
            messages.append(msg)
        else:
            st.error(f"❌ DoorDash 文件格式错误: {msg}")
    my_bar.progress(60)

    if gh_file:
        df_g, msg = process_grubhub(gh_file)
        if df_g is not None:
            dfs.append(df_g)
            messages.append(msg)
        else:
            st.error(f"❌ Grubhub 文件格式错误: {msg}")
    my_bar.progress(90)

    if not dfs:
        st.warning("⚠️ 请至少上传一个有效的 CSV 文件。")
        my_bar.empty()
    else:
        # 显示处理结果
        for msg in messages:
            if "⚠️" in msg:
                st.warning(msg)
            else:
                st.success(msg)
        
        # 核心处理逻辑
        master_df = pd.concat(dfs, ignore_index=True)
        
        summary = master_df.groupby(['Vendor', 'Store_Standard'])[[ 
            'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout'
        ]].sum().reset_index()
        
        # 插入净销售额
        summary.insert(4, 'Net_Sales', summary['Gross_Sales'] + summary['Merchant_Promo'])
        
        # 重命名列为中文
        chinese_cols = {
            'Vendor': '平台',
            'Store_Standard': '标准店名',
            'Gross_Sales': '销售总额',
            'Merchant_Promo': '商家承担折扣',
            'Net_Sales': '净销售额',
            'Commission': '佣金',
            'Marketing': '营销/广告费',
            'Tax_Adj': '税金调整',
            'Other_Fees': '其他费用',
            'Net_Payout': '计算净入账'
        }
        display_df = summary.rename(columns=chinese_cols)
        
        my_bar.progress(100)
        
        # --- 结果展示区 ---
        st.success("✅ 数据处理完成！")
        
        # 汇总指标
        st.subheader("📊 汇总指标")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("总销售额", f"${display_df['销售总额'].sum():,.2f}")
        with col_m2:
            st.metric("总佣金支出", f"${abs(display_df['佣金'].sum()):,.2f}")
        with col_m3:
            st.metric("总净入账", f"${display_df['计算净入账'].sum():,.2f}")
        with col_m4:
            unique_stores = display_df['标准店名'].nunique()
            st.metric("活跃门店数", f"{unique_stores}")
        
        st.subheader("📋 费用拆解明细 (Fee Breakdown)")
        format_dict = {k: "${:,.2f}" for k in chinese_cols.values() if k not in ['平台', '标准店名']}
        st.dataframe(display_df.style.format(format_dict), use_container_width=True)

        # --- Excel 生成 ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            wb = writer.book
            
            fmt_header = wb.add_format({
                'bold': True, 'bg_color': '#0022AB', 'font_color': 'white', 
                'border': 1, 'align': 'center', 'valign': 'vcenter'
            })
            fmt_currency = wb.add_format({'num_format': '$#,##0.00'})
            fmt_currency_red = wb.add_format({'num_format': '$#,##0.00', 'font_color': '#9C0006'})
            fmt_input = wb.add_format({'bg_color': '#FFFFCC', 'border': 1, 'num_format': '$#,##0.00'})
            fmt_bold = wb.add_format({'bold': True, 'border': 1, 'num_format': '$#,##0.00'})

            # Sheet 1: 费用拆解
            s1_name = '费用拆解明细'
            display_df.to_excel(writer, sheet_name=s1_name, index=False, startrow=1)
            ws1 = writer.sheets[s1_name]
            
            for col, h in enumerate(display_df.columns):
                ws1.write(0, col, h, fmt_header)
            
            ws1.set_column('A:A', 12)
            ws1.set_column('B:B', 35)
            ws1.set_column('C:J', 15, fmt_currency)
            ws1.set_column('D:D', 15, fmt_currency_red)
            ws1.set_column('F:I', 15, fmt_currency_red)
            ws1.set_column('J:J', 16, fmt_bold)

            # Sheet 2: 银行对账表
            s2_name = '银行存款核对'
            recon_view = display_df[['平台', '标准店名', '计算净入账']].copy()
            recon_view.to_excel(writer, sheet_name=s2_name, index=False, startrow=1)
            ws2 = writer.sheets[s2_name]
            
            recon_headers = ['平台', '标准店名', '计算净入账 (A)', '银行实际入账 (B) [请填入]', '平台隐藏/周期费用 (C) [请填入]', '最终差异 (A-B+C)']
            for col, h in enumerate(recon_headers):
                ws2.write(0, col, h, fmt_header)

            ws2.set_column('A:A', 12)
            ws2.set_column('B:B', 35)
            ws2.set_column('C:C', 18, fmt_currency)
            ws2.set_column('D:E', 25, fmt_input)
            ws2.set_column('F:F', 18, fmt_bold)

            for i in range(2, len(recon_view) + 2):
                ws2.write_formula(f'F{i}', f'=C{i}-D{i}+E{i}', fmt_bold)
            
            # Sheet 3: 门店映射参考
            s3_name = '门店ID参考'
            store_ref = pd.DataFrame([
                {'门店ID': k, '门店名称': v.split(' - ')[1] if ' - ' in v else v} 
                for k, v in STORE_ID_DISPLAY.items()
            ])
            store_ref.to_excel(writer, sheet_name=s3_name, index=False, startrow=1)
            ws3 = writer.sheets[s3_name]
            for col, h in enumerate(store_ref.columns):
                ws3.write(0, col, h, fmt_header)
            ws3.set_column('A:A', 12)
            ws3.set_column('B:B', 30)
                
        output.seek(0)
        
        # --- 下载区 & 后续指引 ---
        col_download, col_guide = st.columns([1, 2])
        
        with col_download:
            st.download_button(
                label="📥 下载 Excel 对账底稿",
                data=output,
                file_name="Luckin_Finance_Reconciliation_Report.xlsx",
                mime="application/vnd.ms-excel"
            )
        
        with col_guide:
            st.info("""
            **👩‍💻 会计团队后续操作指引 (Next Steps):**
            
            1.  **下载文件**: 点击左侧按钮保存 Excel 文件。
            2.  **打开 Sheet 2 (银行存款核对)**:
                *   **黄色列 D**: 填入银行流水中实际收到的金额。
                *   **黄色列 E**: 填入 CSV 中未体现的平台调整项（如 UberEats 的 EzReward、Membership Fee，或 DoorDash 的跨周期打款）。
            3.  **检查差异**: 确保最后一列 "最终差异" 归零或在允许误差范围内。
            4.  **入账**: 使用 Sheet 1 的明细数据录入 ERP 系统。
            """)

# --- 页脚 ---
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>瑞幸咖啡财务对账系统 v2.0</p>
    <p style='font-size: 0.9rem;'>✅ 门店映射已修复 (US00001-US00006) • 支持 UberEats / DoorDash / Grubhub</p>
</div>
""", unsafe_allow_html=True)
