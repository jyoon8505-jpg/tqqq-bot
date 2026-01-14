import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

# ==========================================
# 1. 기본 설정 및 스타일
# ==========================================
st.set_page_config(page_title="TQQQ Master Pro", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .metric-card { background-color: #0e1117; border: 1px solid #303030; border-radius: 10px; padding: 20px; text-align: center; }
    .stSuccess { color: #00ff00 !important; }
    .stWarning { color: #ffa500 !important; }
    .stError { color: #ff4b4b !important; }
    thead tr th:first-child { display:none }
    tbody th { display:none }
    .stDataFrame { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

# 파일 경로
SHORT_JOURNAL = "short_term_journal.csv"
LONG_PORTFOLIO = "long_term_portfolio.csv"
LONG_BALANCE = "long_term_balance.csv"
LONG_JOURNAL = "long_term_journal.csv" 

# 파라미터
RSI_P = 3
SLOPE_LAG = 2
TP_HALF = 6.0
TP_FULL = 12.0
SL_PCT = -6.0

# ==========================================
# 2. 데이터 로딩 (실시간 기능 강화)
# ==========================================
def get_live_price(ticker):
    """
    야후 파이낸스에서 가장 최신의 1분봉 데이터를 가져옵니다.
    (장중, 프리마켓, 애프터마켓 포함)
    """
    try:
        # prepost=True 옵션이 핵심 (장외 거래 포함)
        data = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=True)
        if not data.empty:
            return float(data['Close'].iloc[-1]) # 가장 최근 거래가 리턴
        else:
            return None
    except:
        return None

@st.cache_data(ttl=300) # 5분 캐시
def load_market_data():
    start_date = "2010-02-15"
    tickers = ["TQQQ", "QLD", "QQQ", "KRW=X"]
    try:
        # 1. 지표 계산용 일봉 데이터 (기존 방식)
        df = yf.download(tickers, start=start_date, progress=False, group_by='ticker', auto_adjust=False)
        if df is None or df.empty: return pd.DataFrame(), {}
        
        data = pd.DataFrame(index=df.index)
        try:
            data['T_Close'] = df['TQQQ']['Close']; data['Q_Close'] = df['QQQ']['Close']
            
            # 환율
            if 'KRW=X' in df.columns or ('KRW=X', 'Close') in df.columns:
                data['USDKRW'] = df['KRW=X']['Close']
            else: data['USDKRW'] = 1450.0 
        except: return pd.DataFrame(), {}

        data['USDKRW'] = data['USDKRW'].ffill().fillna(1450.0)
        data.dropna(subset=['T_Close', 'Q_Close'], inplace=True)
        
        # 지표 계산
        data['Q_MA50'] = data['Q_Close'].rolling(window=50).mean()
        data['Q_MA200'] = data['Q_Close'].rolling(window=200).mean()
        data['ExitLine'] = data['Q_MA200'] * 0.975
        
        # RSI 3 (안정성 강화)
        delta = data['Q_Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=3).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=3).mean()
        loss = loss.replace(0, 0.00001)
        rs = (gain / loss).replace([np.inf, -np.inf], np.nan)
        data['Q_RSI3'] = 100 - (100 / (1 + rs))
        data['Q_RSI3'] = data['Q_RSI3'].fillna(50)
        
        # 모멘텀
        ma20 = data['Q_Close'].rolling(window=20).mean()
        slope = ma20.pct_change() * 100
        data['Slope_Accel'] = slope > slope.shift(2)
        
        final_df = data.dropna()
        
        # 2. 실시간 가격 가져오기 (Live)
        live_prices = {
            'TQQQ': get_live_price("TQQQ"),
            'QLD': get_live_price("QLD"),
            'QQQ': get_live_price("QQQ"),
            'KRW': data['USDKRW'].iloc[-1]
        }
        
        # 실시간 가격을 못 가져오면 일봉 종가로 대체
        if live_prices['TQQQ'] is None: live_prices['TQQQ'] = final_df['T_Close'].iloc[-1]
        if live_prices['QQQ'] is None: live_prices['QQQ'] = final_df['Q_Close'].iloc[-1]
        # QLD는 데이터프레임에 없으므로 별도 처리 필요하지만 여기선 생략하거나 TQQQ 로직 따름
        
        return final_df, live_prices
        
    except Exception as e:
        return pd.DataFrame(), {}

# ==========================================
# 3. 메인 로직
# ==========================================
st.sidebar.title("💎 TQQQ Master")
mode = st.sidebar.radio("모드 선택", ["🏹 단기 스나이퍼", "🚜 장기 졸업 프로젝트"])

with st.spinner("🚀 실시간 시세 조회 중..."):
    df, live_data = load_market_data()

if df.empty: st.error("데이터 로드 실패. 다시 시도해주세요."); st.stop()

last = df.iloc[-1]
curr_date = df.index[-1].date()
usd_krw = live_data.get('KRW', 1450.0)

# ★ 핵심: 화면에 표시할 때는 '실시간 가격' 우선 사용
tqqq_price = live_data.get('TQQQ', last['T_Close'])
qqq_price_live = live_data.get('QQQ', last['Q_Close'])
qld_price_live = live_data.get('QLD', 0.0) 
if qld_price_live == 0.0 or qld_price_live is None: # QLD 실시간 실패시 보정
     qld_price_live = tqqq_price * 0.7 # 임시 비율(단순 예시) 혹은 0처리

# ==============================================================================
# MODE A: 🏹 단기 스나이퍼
# ==============================================================================
if mode == "🏹 단기 스나이퍼":
    st.title("🏹 단기 스나이퍼 (Live)")
    st.caption(f"기준 시간: {datetime.now().strftime('%H:%M:%S')} | TQQQ 현재가: ${tqqq_price:.2f}")
    
    # 저널 로드
    def load_short_journal():
        if not os.path.exists(SHORT_JOURNAL):
            return pd.DataFrame(columns=['ID','Date','Type','Price','Shares','TP_Half','TP_Full','SL','Status','Profit','Note'])
        return pd.read_csv(SHORT_JOURNAL)
    
    journal = load_short_journal()

    tab1, tab2, tab3 = st.tabs(["🏠 내 자산 현황", "🚦 오늘 판독기", "📒 매매일지"])

    # --- Tab 1: 자산 현황 ---
    with tab1:
        st.header(f"💰 내 자산 현황")
        
        open_trades = journal[journal['Status'].isin(['Open', 'Half_Open'])].copy()
        total_invested = 0
        current_val = 0
        unrealized_pnl = 0
        
        if not open_trades.empty:
            total_invested = (open_trades['Price'] * open_trades['Shares']).sum()
            current_val = (tqqq_price * open_trades['Shares']).sum()
            unrealized_pnl = current_val - total_invested

        realized_profit = journal['Profit'].sum()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 매수 금액", f"${total_invested:,.2f}")
        m2.metric("총 평가 자산", f"${current_val:,.2f}", delta=f"${unrealized_pnl:,.2f}")
        m3.metric("실현 수익금", f"${realized_profit:,.2f}", delta_color="normal")
        
        return_rate = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
        m4.metric("수익률", f"{return_rate:.2f}%")

        st.divider()
        st.subheader("📦 보유 계좌 상세")
        if not open_trades.empty:
            open_trades['Current_Price'] = tqqq_price
            open_trades['Return(%)'] = (tqqq_price - open_trades['Price']) / open_trades['Price'] * 100
            open_trades['Value($)'] = open_trades['Shares'] * tqqq_price
            
            display_df = open_trades[['ID', 'Date', 'Shares', 'Price', 'Current_Price', 'Return(%)', 'Value($)', 'Status']]
            display_df.columns = ['ID', '매수일', '수량', '평단가', '현재가', '수익률', '평가금액', '상태']
            
            st.dataframe(
                display_df.style.format({
                    '평단가': '${:.2f}', '현재가': '${:.2f}', 
                    '수익률': '{:.2f}%', '평가금액': '${:,.2f}'
                }).applymap(lambda x: 'color: red' if x < 0 else 'color: green', subset=['수익률']),
                use_container_width=True
            )
        else:
            st.info("보유 중인 종목이 없습니다.")

    # --- Tab 2: 오늘 판독기 ---
    with tab2:
        is_bull = last['Q_Close'] >= last['Q_MA200']
        rsi_th = 90 if is_bull else 80
        curr_rsi = last['Q_RSI3']
        curr_slope = last['Slope_Accel']
        
        # 지표는 일봉 기준(안정성), 가격은 실시간 표시
        c1, c2, c3 = st.columns(3)
        c1.metric("추세 (MA200)", "Bull" if is_bull else "Bear")
        c2.metric(f"RSI(3)", f"{curr_rsi:.2f}", f"기준 {rsi_th}")
        c3.metric("QQQ 현재가", f"${qqq_price_live:.2f}")
        
        st.divider()
        if (curr_rsi < rsi_th) and curr_slope:
            st.success("## 🔥 [진입 신호] 오늘 종가(LOC) 매수!")
            st.markdown(f"**손절 {SL_PCT}% / 반익 {TP_HALF}% / 완익 {TP_FULL}%**")
        else:
            st.info("## 💤 [관망] 진입 조건 대기 중")
            
        st.divider()
        st.subheader("📋 보유 포지션 분석")
        
        open_trades = journal[journal['Status'].isin(['Open', 'Half_Open'])].copy()
        
        if not open_trades.empty:
            open_trades['Date'] = pd.to_datetime(open_trades['Date'])
            open_trades['Holding_Days'] = (datetime.today() - open_trades['Date']).dt.days
            open_trades['D-Day'] = open_trades['Holding_Days'].apply(lambda x: f"{x}일차")
            
            open_trades['Exp_Half'] = open_trades['Price'] * (1 + TP_HALF/100)
            open_trades['Exp_Full'] = open_trades['Price'] * (1 + TP_FULL/100)
            open_trades['Exp_SL'] = open_trades['Price'] * (1 + SL_PCT/100)
            open_trades['Return(%)'] = (tqqq_price - open_trades['Price']) / open_trades['Price'] * 100
            
            view_df = open_trades[['ID', 'Date', 'Price', 'Shares', 'Return(%)', 'Exp_Half', 'Exp_Full', 'Exp_SL', 'D-Day']]
            view_df['Date'] = view_df['Date'].dt.date
            view_df.columns = ['ID', '매수일', '평단가', '수량', '수익률', '반익절가', '완익절가', '손절가', '보유일']
            
            st.dataframe(
                view_df.style.format({
                    '평단가': '${:.2f}', '반익절가': '${:.2f}', '완익절가': '${:.2f}', '손절가': '${:.2f}',
                    '수익률': '{:.2f}%'
                }).applymap(lambda x: 'color: red' if x < 0 else 'color: green', subset=['수익률']),
                use_container_width=True
            )

    # --- Tab 3: 매매일지 ---
    with tab3:
        st.subheader("📝 단기 매매 기록")
        
        with st.expander("➕ 매수 기록 추가", expanded=False):
            c1, c2, c3 = st.columns(3)
            bd = c1.date_input("매수일", datetime.today())
            bp = c2.number_input("매수가($)", 0.0)
            bq = c3.number_input("수량", 1)
            if st.button("매수 저장"):
                nid = len(journal)+1 if len(journal)>0 else 1
                new_row = {
                    'ID':nid, 'Date':bd, 'Type':'Buy', 'Price':bp, 'Shares':bq,
                    'TP_Half':bp*(1+TP_HALF/100), 'TP_Full':bp*(1+TP_FULL/100), 'SL':bp*(1+SL_PCT/100),
                    'Status':'Open', 'Profit':0.0, 'Note':'-'
                }
                journal = pd.concat([journal, pd.DataFrame([new_row])], ignore_index=True)
                journal.to_csv(SHORT_JOURNAL, index=False)
                st.rerun()

        with st.expander("➖ 매도(익절/손절) 기록 추가", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            sd = c1.date_input("매도일", datetime.today())
            sp = c2.number_input("매도단가($)", 0.0)
            sq = c3.number_input("매도수량", 1)
            sprofit = c4.number_input("실현손익($)", 0.0)
            
            if st.button("매도 기록 저장"):
                nid = len(journal)+1 if len(journal)>0 else 1
                new_row = {
                    'ID':nid, 'Date':sd, 'Type':'Sell', 'Price':sp, 'Shares':sq,
                    'TP_Half':0, 'TP_Full':0, 'SL':0,
                    'Status':'Closed', 'Profit':sprofit, 'Note':'Manual Sell'
                }
                journal = pd.concat([journal, pd.DataFrame([new_row])], ignore_index=True)
                journal.to_csv(SHORT_JOURNAL, index=False)
                st.success("매도 기록 저장 완료"); st.rerun()
        
        if not journal.empty:
            st.markdown("##### 📜 거래 관리 리스트")
            edit_df = journal.copy()
            edit_df['PnL(%)'] = (tqqq_price - edit_df['Price']) / edit_df['Price'] * 100
            
            for idx, row in edit_df.sort_values('ID', ascending=False).iterrows():
                with st.container(border=True):
                    col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 3])
                    
                    if row['Type'] == 'Sell':
                        status_icon = "🔵"; type_str = "매도"
                    else:
                        status_icon = "🟢" if row['Status'] in ['Open', 'Half_Open'] else "⚪"; type_str = "매수"

                    col1.write(f"**#{row['ID']}** {status_icon}")
                    col2.write(f"{row['Date']}")
                    col3.write(f"{type_str}: ${row['Price']:.2f} ({row['Shares']}주)")
                    
                    if row['Status'] in ['Open', 'Half_Open'] and row['Type'] == 'Buy':
                        p_col = "green" if row['PnL(%)'] > 0 else "red"
                        col4.markdown(f"수익률: :{p_col}[{row['PnL(%)']:.2f}%]")
                        
                        action = col5.selectbox("매도/관리", ["-", "반익절 (50%)", "전량 익절 (Win)", "전량 손절 (Loss)", "기록 삭제"], key=f"act_{row['ID']}")
                        
                        if action != "-" and action != "기록 삭제":
                            exec_price = col5.number_input("실제 체결가($)", value=float(tqqq_price), key=f"pr_{row['ID']}")
                            
                            if st.button(f"실행 ({action})", key=f"btn_{row['ID']}"):
                                if action == "반익절 (50%)":
                                    sold_shares = row['Shares'] / 2
                                    profit = (exec_price - row['Price']) * sold_shares
                                    journal.at[idx, 'Status'] = 'Half_Open'
                                    journal.at[idx, 'Profit'] += profit
                                    journal.at[idx, 'Shares'] = sold_shares 
                                elif action in ["전량 익절 (Win)", "전량 손절 (Loss)"]:
                                    profit = (exec_price - row['Price']) * row['Shares']
                                    journal.at[idx, 'Status'] = 'Closed'
                                    journal.at[idx, 'Profit'] += profit
                                    journal.at[idx, 'Shares'] = 0
                                journal.to_csv(SHORT_JOURNAL, index=False); st.rerun()
                        
                        elif action == "기록 삭제":
                            if st.button("삭제", key=f"del_{row['ID']}"):
                                journal = journal.drop(idx); journal.to_csv(SHORT_JOURNAL, index=False); st.rerun()
                    else:
                        p_col = "green" if row['Profit'] > 0 else "red"
                        col4.markdown(f"확정손익: :{p_col}[${row['Profit']:.2f}]")
                        if col5.button("🗑️ 삭제", key=f"del_c_{row['ID']}"):
                            journal = journal.drop(idx); journal.to_csv(SHORT_JOURNAL, index=False); st.rerun()

# ==============================================================================
# MODE B: 🚜 장기 졸업 프로젝트
# ==============================================================================
elif mode == "🚜 장기 졸업 프로젝트":
    st.title("🚜 장기 졸업 프로젝트 (Live)")
    
    if not os.path.exists(LONG_PORTFOLIO):
        # 초기화 데이터
        init_data = [{"Account": 1, "Ticker": "TQQQ", "Shares": 0, "Avg_Price": 0.0, "Level": 0}]
        pd.DataFrame(init_data).to_csv(LONG_PORTFOLIO, index=False)
    if not os.path.exists(LONG_BALANCE):
        pd.DataFrame([{"KRW": 16000000}]).to_csv(LONG_BALANCE, index=False)
    if not os.path.exists(LONG_JOURNAL):
        pd.DataFrame(columns=['Date', 'Account', 'Type', 'Qty', 'Price', 'Amount', 'Note']).to_csv(LONG_JOURNAL, index=False)

    pf_df = pd.read_csv(LONG_PORTFOLIO)
    bal_df = pd.read_csv(LONG_BALANCE)
    log_df = pd.read_csv(LONG_JOURNAL)
    cash_krw = float(bal_df.iloc[0]['KRW'])

    t1, t2, t3, t4 = st.tabs(["🏠 내 자산 현황", "🚦 오늘의 지령", "📒 매매일지", "⚙️ 관리"])

    with t1:
        st.header("📦 계좌별 현황")
        rows = []
        total_invest_krw = 0; total_eval_krw = 0
        
        for idx, row in pf_df.iterrows():
            ticker = row['Ticker']
            shares = row['Shares']
            avg = row['Avg_Price']
            # 실시간 가격 적용
            if ticker == 'TQQQ': cur_p = tqqq_price
            elif ticker == 'QQQ': cur_p = qqq_price_live
            elif ticker == 'QLD': cur_p = qld_price_live if qld_price_live else tqqq_price*0.7
            else: cur_p = tqqq_price # 예외처리

            invest_krw = shares * avg * usd_krw
            eval_krw = shares * cur_p * usd_krw
            total_invest_krw += invest_krw; total_eval_krw += eval_krw
            pnl_pct = (cur_p - avg) / avg * 100 if avg > 0 else 0
            
            rows.append({
                "계좌": f"#{row['Account']}", "종목": ticker, "수량": shares,
                "평단": f"${avg:.2f}", "현재가": f"${cur_p:.2f}",
                "수익률": f"{pnl_pct:.2f}%", "평가액": f"{eval_krw:,.0f}"
            })
        
        total_asset = cash_krw + total_eval_krw
        total_pnl = total_eval_krw - total_invest_krw
        total_ret = (total_pnl / total_invest_krw * 100) if total_invest_krw > 0 else 0
        
        df_view = pd.DataFrame(rows)
        c1, c2, c3 = st.columns(3)
        c1.metric("총 자산", f"{total_asset:,.0f} 원")
        c2.metric("보유 현금", f"{cash_krw:,.0f} 원")
        c3.metric("주식 수익", f"{total_ret:.2f}%", delta=f"{total_pnl:,.0f} 원")
        st.divider(); st.dataframe(df_view, use_container_width=True)

    with t2:
        ma50 = last['Q_MA50']; ma200 = last['Q_MA200']; exit_l = last['ExitLine']
        # 위치 판독은 실시간 QQQ 가격 기준
        q_c = qqq_price_live 
        
        st.subheader("📢 QQQ 위치 판독 (Live)")
        status_data = [
            {"지표": "MA50 (공격)", "기준": f"${ma50:.2f}", "현재": f"${q_c:.2f}", "상태": "🟢 위" if q_c > ma50 else "⚪ 아래"},
            {"지표": "MA200 (방어)", "기준": f"${ma200:.2f}", "현재": f"${q_c:.2f}", "상태": "🟢 위" if q_c > ma200 else "🔴 아래"},
            {"지표": "Exit Line", "기준": f"${exit_l:.2f}", "현재": f"${q_c:.2f}", "상태": "🟢 위" if q_c > exit_l else "🚨 붕괴"},
        ]
        st.dataframe(pd.DataFrame(status_data), use_container_width=True)
        
        st.subheader("💰 익절 체크")
        cnt=0
        for idx, row in pf_df.iterrows():
            if row['Ticker'] == 'TQQQ': cur = tqqq_price
            elif row['Ticker'] == 'QLD': cur = qld_price_live if qld_price_live else 0
            else: cur = 0
            
            if cur > 0 and row['Avg_Price'] > 0:
                pnl = (cur - row['Avg_Price'])/row['Avg_Price']*100
                tgt = int(pnl/20)
                if tgt > row['Level'] and row['Shares']>0:
                    qty = int(row['Shares']*0.1)
                    st.warning(f"🔔 #{row['Account']} 수익 {pnl:.1f}%! {qty}주 매도"); cnt+=1
        if cnt==0: st.info("✅ 특이사항 없음")

    with t3:
        st.subheader("📒 매매 기록")
        with st.expander("➕ 기록 추가", expanded=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            ld = c1.date_input("날짜", datetime.today())
            la = c2.selectbox("계좌", [1, 2, 3, 4])
            lt = c3.selectbox("구분", ["매수", "매도(익절)", "매도(손절)"])
            lq = c4.number_input("수량", 1)
            lp = c5.number_input("단가", 0.0)
            if st.button("저장"):
                amt = lq * lp
                new_log = {'Date':ld, 'Account':la, 'Type':lt, 'Qty':lq, 'Price':lp, 'Amount':amt, 'Note':'-'}
                log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
                log_df.to_csv(LONG_JOURNAL, index=False); st.rerun()
        if not log_df.empty:
            st.dataframe(log_df.sort_index(ascending=False), use_container_width=True)
            if st.button("최근 기록 삭제"):
                log_df = log_df[:-1]; log_df.to_csv(LONG_JOURNAL, index=False); st.rerun()

    with t4:
        with st.expander("💵 현금 관리"):
            amt = st.number_input("금액", step=10000)
            if st.button("입금"): bal_df.iloc[0]['KRW']+=amt; bal_df.to_csv(LONG_BALANCE, index=False); st.rerun()
            if st.button("출금"): bal_df.iloc[0]['KRW']-=amt; bal_df.to_csv(LONG_BALANCE, index=False); st.rerun()
        st.write("📊 데이터 수정")
        new_pf = st.data_editor(pf_df, num_rows="dynamic")
        if st.button("저장"): new_pf.to_csv(LONG_PORTFOLIO, index=False); st.rerun()
