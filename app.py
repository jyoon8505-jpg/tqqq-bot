import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

# ==========================================
# 1. 기본 설정 및 스타일
# ==========================================
st.set_page_config(page_title="TQQQ Master Pro", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .metric-card { background-color: #0e1117; border: 1px solid #303030; border-radius: 10px; padding: 20px; text-align: center; }
    .stSuccess { color: #00ff00 !important; }
    .stWarning { color: #ffa500 !important; }
    .stError { color: #ff4b4b !important; }
    thead tr th:first-child { display:none }
    tbody th { display:none }
    /* 테이블 가독성 */
    .stDataFrame { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

# 파일 경로
SHORT_JOURNAL = "short_term_journal.csv"
LONG_PORTFOLIO = "long_term_portfolio.csv"
LONG_BALANCE = "long_term_balance.csv"
LONG_JOURNAL = "long_term_journal.csv" # 장기 매매일지 추가

# 파라미터 고정 (상수)
RSI_P = 3
SLOPE_LAG = 2
TP_HALF = 6.0
TP_FULL = 12.0
SL_PCT = -6.0

# ==========================================
# 2. 데이터 로딩 (개선판)
# ==========================================
@st.cache_data(ttl=1800)
def load_market_data():
    start_date = "2010-02-15"
    tickers = ["TQQQ", "QLD", "QQQ", "KRW=X"]
    try:
        df = yf.download(tickers, start=start_date, progress=False, group_by='ticker', auto_adjust=False)
        if df is None or df.empty: return pd.DataFrame()
        
        data = pd.DataFrame(index=df.index)
        try:
            data['T_Close'] = df['TQQQ']['Close']; data['T_Open'] = df['TQQQ']['Open']
            data['L_Close'] = df['QLD']['Close']
            data['Q_Close'] = df['QQQ']['Close']
            if 'KRW=X' in df.columns or ('KRW=X', 'Close') in df.columns:
                data['USDKRW'] = df['KRW=X']['Close']
            else: data['USDKRW'] = 1450.0 
        except: return pd.DataFrame()

        data['USDKRW'] = data['USDKRW'].ffill().fillna(1450.0)
        data.dropna(subset=['T_Close', 'Q_Close'], inplace=True)
        
        # 장기 지표
        data['Q_MA50'] = data['Q_Close'].rolling(window=50).mean()
        data['Q_MA200'] = data['Q_Close'].rolling(window=200).mean()
        data['ExitLine'] = data['Q_MA200'] * 0.975
        
        # 단기 지표 (RSI 3 SMA)
        delta = data['Q_Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=3).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=3).mean()
        rs = (gain / loss).replace([np.inf, -np.inf], np.nan)
        data['Q_RSI3'] = 100 - (100 / (1 + rs))
        
        # 모멘텀
        ma20 = data['Q_Close'].rolling(window=20).mean()
        slope = ma20.pct_change() * 100
        data['Slope_Accel'] = slope > slope.shift(2)
        
        return data.dropna()
    except: return pd.DataFrame()

# ==========================================
# 3. 메인 로직
# ==========================================
st.sidebar.title("💎 TQQQ Master")
mode = st.sidebar.radio("모드 선택", ["🏹 단기 스나이퍼", "🚜 장기 졸업 프로젝트"])

with st.spinner("시장 데이터 동기화 중..."):
    df = load_market_data()

if df.empty: st.error("데이터 로드 실패. 다시 시도해주세요."); st.stop()

last = df.iloc[-1]
curr_date = df.index[-1].date()
usd_krw = last['USDKRW']
tqqq_price = last['T_Close']

# ==============================================================================
# MODE A: 🏹 단기 스나이퍼
# ==============================================================================
if mode == "🏹 단기 스나이퍼":
    st.title("🏹 단기 스나이퍼 (Short-Term)")
    
    # 저널 로드
    def load_short_journal():
        if not os.path.exists(SHORT_JOURNAL):
            return pd.DataFrame(columns=['ID','Date','Type','Price','Shares','TP_Half','TP_Full','SL','Status','Profit','Note'])
        return pd.read_csv(SHORT_JOURNAL)
    
    journal = load_short_journal()

    tab1, tab2, tab3 = st.tabs(["🏠 내 자산 현황", "🚦 오늘 판독기", "📒 매매일지"])

    # --- Tab 1: 자산 현황 (실현 손익 추가) ---
    with tab1:
        st.header(f"💰 내 자산 현황 ({curr_date})")
        
        # 보유 중 통계
        open_trades = journal[journal['Status'].isin(['Open', 'Half_Open'])].copy()
        total_invested = 0
        current_val = 0
        unrealized_pnl = 0
        
        if not open_trades.empty:
            total_invested = (open_trades['Price'] * open_trades['Shares']).sum()
            current_val = (tqqq_price * open_trades['Shares']).sum()
            unrealized_pnl = current_val - total_invested

        # 실현 손익 (매매 완료된 건들의 Profit 합계)
        realized_profit = journal['Profit'].sum()
        
        # 총 평가 자산 (보유분 평가액 + 이미 실현한 수익)
        # *주의: 실현 수익은 현금으로 돌아왔다고 가정
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 매수 금액(보유)", f"${total_invested:,.2f}")
        m2.metric("총 평가 자산(보유)", f"${current_val:,.2f}", delta=f"${unrealized_pnl:,.2f}")
        m3.metric("💸 실현 수익금(누적)", f"${realized_profit:,.2f}", delta_color="normal")
        
        # 통합 수익률 (실현+미실현) / (투자원금은 애매하므로 보유분 기준 수익률 표시)
        return_rate = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
        m4.metric("보유분 수익률", f"{return_rate:.2f}%")

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
            st.info("현재 보유 중인 종목이 없습니다.")

    # --- Tab 2: 오늘 판독기 (파라미터 제거됨) ---
    with tab2:
        is_bull = last['Q_Close'] >= last['Q_MA200']
        rsi_th = 90 if is_bull else 80
        curr_rsi = last['Q_RSI3']
        curr_slope = last['Slope_Accel']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("추세 (MA200)", "Bull" if is_bull else "Bear")
        c2.metric(f"RSI(3)", f"{curr_rsi:.2f}", f"기준 {rsi_th}")
        c3.metric("모멘텀", "가속" if curr_slope else "감속")
        
        st.divider()
        if (curr_rsi < rsi_th) and curr_slope:
            st.success("## 🔥 [진입 신호] 오늘 종가(LOC) 매수!")
            st.markdown(f"**손절 {SL_PCT}% / 반익 {TP_HALF}% / 완익 {TP_FULL}%**")
        else:
            st.info("## 💤 [관망] 진입 조건 대기 중")

    # --- Tab 3: 매매일지 (구체화) ---
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
        
        if not journal.empty:
            st.markdown("##### 📜 거래 관리 리스트")
            edit_df = journal.copy()
            edit_df['PnL(%)'] = (tqqq_price - edit_df['Price']) / edit_df['Price'] * 100
            
            for idx, row in edit_df.sort_values('ID', ascending=False).iterrows():
                with st.container(border=True):
                    col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 3])
                    
                    status_icon = "🟢" if row['Status'] in ['Open', 'Half_Open'] else "⚪"
                    col1.write(f"**#{row['ID']}** {status_icon}")
                    col2.write(f"{row['Date']}")
                    col3.write(f"매수: ${row['Price']:.2f} ({row['Shares']}주)")
                    
                    if row['Status'] in ['Open', 'Half_Open']:
                        p_col = "green" if row['PnL(%)'] > 0 else "red"
                        col4.markdown(f"수익률: :{p_col}[{row['PnL(%)']:.2f}%]")
                        
                        # 매도 옵션 (반/전량)
                        action = col5.selectbox("매도/삭제", ["-", "반익절 (50%)", "전량 익절/손절", "기록 삭제"], key=f"act_{row['ID']}", label_visibility="collapsed")
                        
                        if action != "-":
                            if st.button(f"실행 ({action})", key=f"btn_{row['ID']}"):
                                if action == "반익절 (50%)" and row['Status']=='Open':
                                    sold_shares = row['Shares'] / 2
                                    profit = (tqqq_price - row['Price']) * sold_shares
                                    journal.at[idx, 'Status'] = 'Half_Open'
                                    journal.at[idx, 'Profit'] += profit
                                    journal.at[idx, 'Shares'] = sold_shares # 남은 수량 업데이트
                                    
                                elif action == "전량 익절/손절":
                                    profit = (tqqq_price - row['Price']) * row['Shares']
                                    journal.at[idx, 'Status'] = 'Closed'
                                    journal.at[idx, 'Profit'] += profit
                                    journal.at[idx, 'Shares'] = 0
                                    
                                elif action == "기록 삭제":
                                    journal = journal.drop(idx)
                                
                                journal.to_csv(SHORT_JOURNAL, index=False)
                                st.rerun()
                    else:
                        p_col = "green" if row['Profit'] > 0 else "red"
                        col4.markdown(f"확정손익: :{p_col}[${row['Profit']:.2f}]")
                        col5.caption("거래 종료")

# ==============================================================================
# MODE B: 🚜 장기 졸업 프로젝트
# ==============================================================================
elif mode == "🚜 장기 졸업 프로젝트":
    st.title("🚜 장기 졸업 프로젝트 (MA50 Safe)")
    
    # 파일 초기화
    if not os.path.exists(LONG_PORTFOLIO):
        init_data = [
            {"Account": 1, "Ticker": "TQQQ", "Shares": 100, "Avg_Price": 52.93, "Level": 0},
            {"Account": 2, "Ticker": "QLD",  "Shares": 361, "Avg_Price": 70.73, "Level": 0},
            {"Account": 3, "Ticker": "TQQQ", "Shares": 66,  "Avg_Price": 52.66, "Level": 0},
            {"Account": 4, "Ticker": "TQQQ", "Shares": 88,  "Avg_Price": 54.22, "Level": 0}
        ]
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

    # --- Tab 1: 자산 현황 ---
    with t1:
        st.header("📦 계좌별 현황")
        
        rows = []
        total_invest_krw = 0
        total_eval_krw = 0
        
        for idx, row in pf_df.iterrows():
            ticker = row['Ticker']
            shares = row['Shares']
            avg = row['Avg_Price']
            cur_p = last['T_Close'] if ticker == 'TQQQ' else last['L_Close']
            
            invest_krw = shares * avg * usd_krw
            eval_krw = shares * cur_p * usd_krw
            
            total_invest_krw += invest_krw
            total_eval_krw += eval_krw
            pnl_pct = (cur_p - avg) / avg * 100
            
            rows.append({
                "계좌": f"#{row['Account']}", "종목": ticker, "수량": shares,
                "평단($)": f"${avg:.2f}", "현재가($)": f"${cur_p:.2f}",
                "수익률": f"{pnl_pct:.2f}%", "평가액(₩)": f"{eval_krw:,.0f}"
            })
        
        # 합계 계산
        total_asset = cash_krw + total_eval_krw
        total_pnl = total_eval_krw - total_invest_krw
        total_ret = (total_pnl / total_invest_krw * 100) if total_invest_krw > 0 else 0
        
        # 합계 행 추가
        df_view = pd.DataFrame(rows)
        # 1. 대시보드
        c1, c2, c3 = st.columns(3)
        c1.metric("총 평가 자산 (현금포함)", f"{total_asset:,.0f} 원")
        c2.metric("보유 현금", f"{cash_krw:,.0f} 원")
        c3.metric("주식 수익률 (합산)", f"{total_ret:.2f}%", delta=f"{total_pnl:,.0f} 원")
        
        st.divider()
        st.dataframe(df_view, use_container_width=True)
        st.caption(f"적용 환율: {usd_krw:.2f} 원/$")

    # --- Tab 2: 오늘의 지령 ---
    with t2:
        q_c = last['Q_Close']; ma50 = last['Q_MA50']; ma200 = last['Q_MA200']; exit_l = last['ExitLine']
        
        st.subheader("📢 QQQ 위치 판독")
        
        # 한눈에 보기 쉬운 테이블
        status_data = [
            {"지표": "MA50 (공격선)", "기준가": f"${ma50:.2f}", "현재가": f"${q_c:.2f}", "상태": "🟢 위 (상승장)" if q_c > ma50 else "⚪ 아래"},
            {"지표": "MA200 (방어선)", "기준가": f"${ma200:.2f}", "현재가": f"${q_c:.2f}", "상태": "🟢 위" if q_c > ma200 else "🔴 아래 (현금화)"},
            {"지표": "Exit Line (손절선)", "기준가": f"${exit_l:.2f}", "현재가": f"${q_c:.2f}", "상태": "🟢 위 (홀딩)" if q_c > exit_l else "🚨 붕괴 (전량매도)"},
        ]
        st.dataframe(pd.DataFrame(status_data), use_container_width=True)
        
        st.divider()
        
        # 익절 체크
        st.subheader("💰 계좌별 액션 체크")
        cnt=0
        for idx, row in pf_df.iterrows():
            cur = last['T_Close'] if row['Ticker']=='TQQQ' else last['L_Close']
            pnl = (cur - row['Avg_Price'])/row['Avg_Price']*100
            tgt = int(pnl/20)
            if tgt > row['Level'] and row['Shares']>0:
                qty = int(row['Shares']*0.1)
                st.warning(f"🔔 [익절 신호] 계좌 #{row['Account']} 수익 {pnl:.1f}% 도달! {qty}주 매도하세요.")
                cnt+=1
        if cnt==0: st.info("✅ 현재 익절/손절 필요한 계좌가 없습니다. 홀딩하세요.")

    # --- Tab 3: 매매일지 (New) ---
    with t3:
        st.subheader("📒 장기 프로젝트 매매 기록")
        
        with st.expander("➕ 거래 기록 추가", expanded=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            ld = c1.date_input("날짜", datetime.today())
            la = c2.selectbox("계좌", [1, 2, 3, 4])
            lt = c3.selectbox("구분", ["매수", "매도(익절)", "매도(손절)"])
            lq = c4.number_input("수량", 1)
            lp = c5.number_input("단가($)", 0.0)
            
            if st.button("기록 저장 (장기)"):
                amt = lq * lp
                new_log = {'Date':ld, 'Account':la, 'Type':lt, 'Qty':lq, 'Price':lp, 'Amount':amt, 'Note':'-'}
                log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
                log_df.to_csv(LONG_JOURNAL, index=False)
                st.success("저장되었습니다.")
                st.rerun()
        
        if not log_df.empty:
            # 표시용 포맷팅
            disp_log = log_df.copy().sort_index(ascending=False)
            disp_log['Amount'] = disp_log['Amount'].apply(lambda x: f"${x:,.2f}")
            disp_log['Price'] = disp_log['Price'].apply(lambda x: f"${x:.2f}")
            st.dataframe(disp_log, use_container_width=True)
            
            if st.button("맨 위 기록 삭제 (실수 시)"):
                log_df = log_df[:-1]
                log_df.to_csv(LONG_JOURNAL, index=False)
                st.rerun()

    # --- Tab 4: 관리 ---
    with t4:
        with st.expander("💵 현금 관리"):
            amt = st.number_input("금액", step=10000)
            c1, c2 = st.columns(2)
            if c1.button("입금"): bal_df.iloc[0]['KRW']+=amt; bal_df.to_csv(LONG_BALANCE, index=False); st.rerun()
            if c2.button("출금"): bal_df.iloc[0]['KRW']-=amt; bal_df.to_csv(LONG_BALANCE, index=False); st.rerun()
        
        st.write("📊 포트폴리오 데이터 수정")
        new_pf = st.data_editor(pf_df, num_rows="dynamic")
        if st.button("변경사항 저장"): new_pf.to_csv(LONG_PORTFOLIO, index=False); st.rerun()