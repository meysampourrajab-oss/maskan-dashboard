import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import numpy as np

# ۱. تنظیمات اولیه و اتصال به دیتابیس
st.set_page_config(page_title="سامانه هوشمند نهضت ملی مسکن", layout="wide")
conn = sqlite3.connect('housing_justice_v16.db', check_same_thread=False)
cur = conn.cursor()

# ایجاد جداول پایه (اصلاح خطای پرانتز در خط ۱۶)
cur.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, location TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, p_id INTEGER, name TEXT, units INTEGER)')
cur.execute('''CREATE TABLE IF NOT EXISTS members 
               (c_id INTEGER, month TEXT, name TEXT, payment REAL, decile INTEGER, file_prev_block TEXT)''')
cur.execute('CREATE TABLE IF NOT EXISTS blocks (c_id INTEGER, month TEXT, b_id INTEGER, prog REAL, cap INTEGER)')
conn.commit()

# استایل RTL برای ظاهر فارسی
st.markdown("""<style> .main { text-align: right; direction: rtl; } 
    div[data-testid="stSidebar"] { direction: rtl; } 
    th, td { text-align: center !important; } </style>""", unsafe_allow_html=True)

# تابع تخصیص: اولویت ۱ مبلغ واریزی | اولویت ۲ دهک های ۱، ۲ و ۳
def calculate_allocation_logic(df_m, df_b):
    if df_m.empty or df_b.empty:
        return {}, {}, pd.DataFrame()
    
    # تعیین اولویت دهک (فقط برای مبالغ مساوی)
    df_m['decile_priority'] = df_m['decile'].apply(lambda x: 1 if str(x) in ['1','2','3'] else 0)
    
    # مرتب‌سازی: اول مبلغ (نزولی) | دوم اولویت دهک (نزولی)
    m_sorted = df_m.sort_values(by=['payment', 'decile_priority'], ascending=[False, False]).reset_index(drop=True)
    b_sorted = df_b.sort_values(by='prog', ascending=False).reset_index(drop=True)
    
    mapping = {}
    res_list = []
    b_ptr, fill = 0, 0
    b_map_usage = {int(r['b_id']): 0 for _, r in df_b.iterrows()}
    
    for i, m in m_sorted.iterrows():
        if b_ptr < len(b_sorted):
            curr_b = b_sorted.iloc[b_ptr]
            b_id = int(curr_b['b_id'])
            mapping[m['name']] = b_id
            res_list.append({
                'ردیف': i+1, 'نام عضو': m['name'], 'واریزی (ریال)': f"{m['payment']:,.0f}",
                'دهک': m['decile'], 'بلوک جدید': b_id, 'پیشرفت': f"{curr_b['prog']}%",
                'file_prev': m['file_prev_block']
            })
            b_map_usage[b_id] += 1
            fill += 1
            if fill >= int(curr_b['cap']):
                b_ptr += 1
                fill = 0
        else:
            mapping[m['name']] = "عدم تخصیص"
            res_list.append({
                'ردیف': i+1, 'نام عضو': m['name'], 'واریزی (ریال)': f"{m['payment']:,.0f}",
                'دهک': m['decile'], 'بلوک جدید': "عدم تخصیص", 'پیشرفت': "-",
                'file_prev': m['file_prev_block']
            })
    return mapping, b_map_usage, pd.DataFrame(res_list)

# ۲. مدیریت منوی کناری
st.sidebar.title("🏠 سامانه هوشمند نهضت ملی")
mode = st.sidebar.radio("انتخاب بخش:", ["📊 داشبورد مدیریتی", "⚙️ پنل مدیریت و آپلود"])
st.sidebar.divider()

all_projects = pd.read_sql("SELECT * FROM projects", conn)

# --- بخش پنل مدیریت (دارای رمز عبور) ---
if mode == "⚙️ پنل مدیریت و آپلود":
    st.title("🔐 ورود به بخش مدیریت")
    admin_password = st.text_input("رمز عبور مدیر سیستم:", type="password")
    
    if admin_password == "1234": # رمز عبور شما
        st.success("دسترسی مدیریتی تایید شد.")
        t1, t2, t3 = st.tabs(["🏗️ مدیریت پروژه", "🏢 مدیریت شرکت", "📤 آپلود فایل ماهانه"])
        
        with t1:
            st.subheader("تعریف پروژه کلان")
            c1, c2 = st.columns(2)
            p_n, p_l = c1.text_input("نام پروژه"), c2.text_input("محل اجرا")
            if st.button("ثبت پروژه"):
                if p_n:
                    cur.execute("INSERT INTO projects (name, location) VALUES (?,?)", (p_n, p_l))
                    conn.commit(); st.rerun()
            st.dataframe(all_projects, width=1200, hide_index=True)

        with t2:
            if not all_projects.empty:
                st.subheader("تعریف پیمانکار (شرکت)")
                sel_p = st.selectbox("انتخاب پروژه والد:", all_projects['name'].tolist())
                p_id = int(all_projects[all_projects['name'] == sel_p]['id'].iloc[0])
                c1, c2 = st.columns(2)
                c_n, c_u = c1.text_input("نام شرکت پیمانکار"), c2.number_input("تعداد واحد کل شرکت", min_value=1)
                if st.button("ثبت شرکت"):
                    if c_n:
                        cur.execute("INSERT INTO companies (p_id, name, units) VALUES (?,?,?)", (p_id, c_n, c_u))
                        conn.commit(); st.success("شرکت ثبت شد."); st.rerun()
                st.table(pd.read_sql(f"SELECT id, name, units FROM companies WHERE p_id={p_id}", conn))
            else: st.info("ابتدا پروژه تعریف کنید.")

        with t3:
            if not all_projects.empty:
                sel_p_up = st.selectbox("پروژه:", all_projects['name'].tolist(), key="up_p")
                p_id_up = int(all_projects[all_projects['name'] == sel_p_up]['id'].iloc[0])
                comps = pd.read_sql(f"SELECT * FROM companies WHERE p_id={p_id_up}", conn)
                if not comps.empty:
                    sel_c_up = st.selectbox("انتخاب شرکت جهت آپلود:", comps['name'].tolist())
                    c_id_up = int(comps[comps['name'] == sel_c_up]['id'].iloc[0])
                    c1, c2 = st.columns(2)
                    m, y = c1.selectbox("ماه گزارش:", ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور","مهر","آبان","آذر","دی","بهمن","اسفند"]), c2.selectbox("سال:", [1404, 1405])
                    f_date = f"{m} {y}"
                    f_m = st.file_uploader("فایل واریزی اعضا", type=['csv','xlsx'])
                    f_b = st.file_uploader("فایل پیشرفت بلوک‌ها", type=['csv','xlsx'])
                    if st.button("🚀 بارگذاری و پردازش نهایی"):
                        if f_m and f_b:
                            df_m = pd.read_csv(f_m) if f_m.name.endswith('.csv') else pd.read_excel(f_m)
                            df_b = pd.read_csv(f_b) if f_b.name.endswith('.csv') else pd.read_excel(f_b)
                            cur.execute(f"DELETE FROM members WHERE c_id={c_id_up} AND month='{f_date}'")
                            cur.execute(f"DELETE FROM blocks WHERE c_id={c_id_up} AND month='{f_date}'")
                            for _, r in df_m.iterrows():
                                dec = r.iloc[3] if len(r) > 3 else 10
                                pre = str(r.iloc[4]) if len(r) > 4 else "-"
                                cur.execute("INSERT INTO members (c_id, month, name, payment, decile, file_prev_block) VALUES (?,?,?,?,?,?)",
                                            (c_id_up, f_date, r.iloc[1], float(str(r.iloc[2]).replace(',','')), dec, pre))
                            for _, r in df_b.iterrows():
                                cur.execute("INSERT INTO blocks (c_id, month, b_id, prog, cap) VALUES (?,?,?,?,?)",
                                            (c_id_up, f_date, int(r.iloc[0]), float(str(r.iloc[1]).replace('%','')), int(r.iloc[2])))
                            conn.commit(); st.success(f"داده‌های {f_date} ثبت شد.")
    elif admin_password != "":
        st.error("🔑 رمز عبور اشتباه است.")

# --- بخش داشبورد مدیریتی (بدون رمز) ---
else:
    st.title("📊 داشبورد تحلیل و تخصیص هوشمند")
    if all_projects.empty: st.info("پروژه‌ای تعریف نشده است.")
    else:
        c1, c2 = st.columns(2)
        p_name_v = c1.selectbox("انتخاب پروژه:", all_projects['name'].tolist())
        p_id_v = int(all_projects[all_projects['name'] == p_name_v]['id'].iloc[0])
        comps_v = pd.read_sql(f"SELECT * FROM companies WHERE p_id={p_id_v}", conn)
        
        if not comps_v.empty:
            c_name_v = c2.selectbox("انتخاب شرکت پیمانکار:", comps_v['name'].tolist())
            c_id_v = int(comps_v[comps_v['name'] == c_name_v]['id'].iloc[0])
            months = pd.read_sql(f"SELECT DISTINCT month FROM blocks WHERE c_id={c_id_v}", conn)['month'].tolist()
            
            if months:
                view_m = st.select_slider("دوره گزارش:", options=months, value=months[-1])
                prev_m = months[months.index(view_m)-1] if months.index(view_m) > 0 else None
                
                df_m = pd.read_sql(f"SELECT * FROM members WHERE c_id={c_id_v} AND month='{view_m}'", conn)
                df_b = pd.read_sql(f"SELECT * FROM blocks WHERE c_id={c_id_v} AND month='{view_m}'", conn)

                # واکشی تخصیص ماه قبل برای مقایسه
                prev_db_map = {}
                df_b_p = pd.DataFrame()
                if prev_m:
                    df_m_old = pd.read_sql(f"SELECT * FROM members WHERE c_id={c_id_v} AND month='{prev_m}'", conn)
                    df_b_old = pd.read_sql(f"SELECT * FROM blocks WHERE c_id={c_id_v} AND month='{prev_m}'", conn)
                    prev_db_map, _, _ = calculate_allocation_logic(df_m_old, df_b_old)
                    df_b_p = df_b_old

                _, b_usage, df_res = calculate_allocation_logic(df_m, df_b)
                
                st.divider()
                st.subheader("📋 آمار کلیدی پروژه")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("تعداد بلوک", len(df_b)); k1.metric("کل واحدها", int(df_b['cap'].sum()))
                avg_p = df_b['prog'].mean()
                delta_p = f"{avg_p - df_b_p['prog'].mean():.1f}%" if not df_b_p.empty else None
                k2.metric("میانگین پیشرفت", f"{avg_p:.1f}%", delta=delta_p)
                k2.metric("تعداد اعضا", len(df_res))
                if not df_b.empty and df_b['prog'].max() > 0:
                    leader = df_b.loc[df_b['prog'].idxmax()]
                    k3.metric("بلوک پیشرو", f"شماره {int(leader['b_id'])}"); k3.metric("بیشترین پیشرفت", f"{leader['prog']}%")
                k4.metric("واریزی (م.ت)", f"{(df_m['payment'].sum()/10000000):,.0f}"); k4.metric("دوره", view_m)

                tabs = st.tabs(["📋 لیست تخصیص اعضا", "📊 پیشرفت فیزیکی", "📂 ظرفیت بلوک‌ها", "💰 تحلیل واریزی"])
                
                with tabs[0]:
                    def get_pb_val(row):
                        if prev_m and row['نام عضو'] in prev_db_map: return prev_db_map[row['نام عضو']]
                        return row['file_prev']
                    df_res['بلوک قبلی'] = df_res.apply(get_pb_val, axis=1)
                    st.dataframe(df_res[['ردیف', 'نام عضو', 'واریزی (ریال)', 'دهک', 'بلوک جدید', 'بلوک قبلی', 'پیشرفت']], width='stretch', hide_index=True)

                with tabs[1]:
                    if not df_b.empty and df_b['prog'].max() > 0:
                        fig = px.bar(df_b, x='b_id', y='prog', text='prog', color_discrete_sequence=['#2ecc71'])
                        fig.update_layout(xaxis_type='category'); st.plotly_chart(fig, width='stretch')
                    else: st.warning("اطلاعات پیشرفت جهت رسم نمودار موجود نیست.")

                with tabs[2]:
                    cap_t = [{'بلوک': int(b['b_id']), 'ظرفیت': int(b['cap']), 'تخصیص': b_usage.get(int(b['b_id']),0), 'باقی': int(b['cap'])-b_usage.get(int(b['b_id']),0), 'درصد پیشرفت': f"{b['prog']}%"} for _, b in df_b.iterrows()]
                    st.dataframe(pd.DataFrame(cap_t), width='stretch', hide_index=True)

                with tabs[3]:
                    df_m['T'] = df_m['payment'] / 10_000_000
                    bins = [0, 40, 100, 200, 300, 400, 500, 600, 700, np.inf]
                    lbls = ['زیر ۴۰ م','۴۰-۱۰۰ م','۱۰۰-۲۰۰ م','۲۰۰-۳۰۰ م','۳۰۰-۴۰۰ م','۴۰۰-۵۰۰ م','۵۰۰-۶۰۰ م','۶۰۰-۷۰۰ م','بالای ۷۰۰ م']
                    df_m['cat'] = pd.cut(df_m['T'], bins=bins, labels=lbls, include_lowest=True)
                    cts = df_m['cat'].value_counts().reindex(lbls).reset_index(); cts.columns=['بازه','تعداد']
                    cl1, cl2 = st.columns(2)
                    with cl1: st.table(cts)
                    with cl2:
                        if cts['تعداد'].sum() > 0: st.plotly_chart(px.pie(cts, values='تعداد', names='بازه', hole=0.4), width='stretch')
                        else: st.info("داده‌ای برای واریزی یافت نشد.")
            else: st.warning("⚠️ داده‌ای یافت نشد.")
