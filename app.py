import streamlit as st
import pandas as pd
import io
import csv
from PIL import Image

# ==========================================
# 🎨 页面配置与 CSS 样式 (Luckin 风格)
# ==========================================
st.set_page_config(page_title="瑞幸咖啡财务对账系统", layout="wide", page_icon="☕")

# 瑞幸蓝: #0022AB (近似)
luckin_blue = "#0022AB"

st.markdown(f"""
    <style>
    /* 全局字体优化 */
    .main {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }}
    /* 按钮样式覆盖 - 瑞幸蓝 */
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
        background-color: #00187A; /* 深一点的蓝色 */
        color: white;
    }}
    /* 标题样式 */
    h1, h2, h3 {{
        color: #333333;
    }}
    /* 提示框样式 */
    .stAlert {{
        background-color: #EEF4FF;
        border-left: 5px solid {luckin_blue};
    }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🧠 核心逻辑 & 映射
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
    if pd.isna(raw_text): return '未知门店'
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
# 🟦 平台数据处理 (保持逻辑不变，优化输出)
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
        if matches: return df[matches[0]].apply(clean_num)
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

# --- Logo & Header ---
try:
    # 尝试加载 logo (请确保文件名为 logo.png 或 logo.jpg 且在同一目录)
    st.image("logo.png", width=150) 
except:
    # 如果没有 logo 文件，显示文字备选
    st.markdown(f"<h1 style='color:{luckin_blue};'>luckin coffee</h1>", unsafe_allow_html=True)

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
    
    # 进度条
    my_bar = st.progress(0)
    
    if uber_file:
        df_u = process_ubereats(uber_file)
        if df_u is not None: dfs.append(df_u)
        else: st.error("❌ UberEats 文件格式错误，请检查表头。")
    my_bar.progress(30)
            
    if dd_file:
        df_d = process_doordash(dd_file)
        if df_d is not None: dfs.append(df_d)
        else: st.error("❌ DoorDash 文件格式错误，请检查表头。")
    my_bar.progress(60)

    if gh_file:
        df_g = process_grubhub(gh_file)
        if df_g is not None: dfs.append(df_g)
        else: st.error("❌ Grubhub 文件格式错误，请检查表头。")
    my_bar.progress(90)

    if not dfs:
        st.warning("⚠️ 请至少上传一个有效的 CSV 文件。")
        my_bar.empty()
    else:
        # 核心处理逻辑
        master_df = pd.concat(dfs, ignore_index=True)
        
        summary = master_df.groupby(['Vendor', 'Store_Standard'])[[ 
            'Gross_Sales', 'Merchant_Promo', 'Commission', 'Marketing', 'Tax_Adj', 'Other_Fees', 'Net_Payout'
        ]].sum().reset_index()
        
        # 插入净销售额
        summary.insert(4, 'Net_Sales', summary['Gross_Sales'] + summary['Merchant_Promo'])
        
        # 重命名列为中文（用于展示和导出）
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
        
        st.subheader("📊 费用拆解预览 (Fee Breakdown)")
        # 格式化显示
        format_dict = {k: "${:,.2f}" for k in chinese_cols.values() if k not in ['平台', '标准店名']}
        st.dataframe(display_df.style.format(format_dict))

        # --- Excel 生成 ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            wb = writer.book
            
            # 定义 Excel 样式
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
            
            # 写入中文表头
            for col, h in enumerate(display_df.columns):
                ws1.write(0, col, h, fmt_header)
            
            ws1.set_column('A:B', 20) # 平台、店名
            ws1.set_column('C:J', 15, fmt_currency)
            ws1.set_column('D:D', 15, fmt_currency_red) # 折扣红字
            ws1.set_column('F:I', 15, fmt_currency_red) # 费用红字
            ws1.set_column('J:J', 16, fmt_bold) # 净入账加粗

            # Sheet 2: 银行对账表
            s2_name = '银行存款核对'
            recon_view = display_df[['平台', '标准店名', '计算净入账']].copy()
            recon_view.to_excel(writer, sheet_name=s2_name, index=False, startrow=1)
            ws2 = writer.sheets[s2_name]
            
            recon_headers = ['平台', '标准店名', '计算净入账 (A)', '银行实际入账 (B) [请填入]', '平台隐藏/周期费用 (C) [请填入]', '最终差异 (A-B+C)']
            for col, h in enumerate(recon_headers):
                ws2.write(0, col, h, fmt_header)

            ws2.set_column('A:B', 20)
            ws2.set_column('C:C', 18, fmt_currency)
            ws2.set_column('D:E', 20, fmt_input) # 黄色填报区
            ws2.set_column('F:F', 18, fmt_bold)

            # 写入差异公式
            for i in range(2, len(recon_view) + 2):
                ws2.write_formula(f'F{i}', f'=C{i}-D{i}+E{i}', fmt_bold)
                
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
