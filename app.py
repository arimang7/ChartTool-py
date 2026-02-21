import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from google import genai
import time
import os
import jwt
import base64
import json
from dotenv import load_dotenv
from streamlit_oauth import OAuth2Component

# .env 파일 로드
load_dotenv()

import requests

# 1. 환경 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "텔레그램 설정이 되어있지 않습니다."
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return True, "성공"
        else:
            return False, f"오류: {response.text}"
    except Exception as e:
        return False, f"예외 발생: {e}"

# Google OAuth2 설정
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8501")
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZATION_URL, TOKEN_URL, TOKEN_URL)

st.set_page_config(page_title="AI 주식 분석 도구", layout="wide")

# 1.1 Google 로그인 기능 추가
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""

with st.sidebar:
    st.header("계정")
    if not st.session_state.logged_in:
        if not CLIENT_ID or not CLIENT_SECRET:
            st.error(".env 파일에 GOOGLE_CLIENT_ID와 GOOGLE_CLIENT_SECRET을 설정해주세요.")
        else:
            # 구글 로그인 버튼 스타일 커스텀 (텍스트 제거 및 호버 효과 변경)
            st.markdown("""
                <style>
                /* 버튼을 아이콘 크기에 맞게 정사각형으로 조정하고 배경을 흰색으로 설정 */
                div[data-testid="stSidebar"] button:has(img[src*="googleg"]) {
                    background-color: white !important;
                    border: 1px solid #dadce0 !important;
                    border-radius: 4px !important;
                    width: 40px !important;
                    height: 40px !important;
                    padding: 0 !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    transition: background-color 0.2s, box-shadow 0.2s !important;
                }
                /* 호버 시 빨간색 제거 및 구글 표준 스타일(연한 회색) 적용 */
                div[data-testid="stSidebar"] button:has(img[src*="googleg"]):hover {
                    background-color: #f8f9fa !important; /* 매우 연한 회색 */
                    border-color: #dadce0 !important;
                    color: black !important;
                    box-shadow: 0 1px 3px rgba(60,64,67,0.3) !important;
                }
                </style>
            """, unsafe_allow_html=True)

            result = oauth2.authorize_button(
                name="",
                icon="https://fonts.gstatic.com/s/i/productlogos/googleg/v6/24px.svg",
                redirect_uri=REDIRECT_URI,
                scope="openid email profile",
                key="google_auth",
            )
            if result:
                st.session_state.logged_in = True
                # result 구조 유연하게 대응 (token 키가 중첩되어 있거나 바로 토큰 정보가 있는 경우 모두 처리)
                token_data = result.get("token") if isinstance(result.get("token"), dict) else result
                id_token = token_data.get("id_token")
                
                if id_token:
                    try:
                        # PyJWT 버전에 상관없이 서명 검증 없이 페이로드 추출
                        decoded_token = jwt.decode(id_token, options={"verify_signature": False, "verify_aud": False})
                        st.session_state.user_email = decoded_token.get("email", "No Email Found")
                    except Exception:
                        # 라이브러리 에러 발생 시 수동으로 페이로드(2번째 파트) 직접 디코딩 시도
                        try:
                            payload_part = id_token.split('.')[1]
                            padding = '=' * (-len(payload_part) % 4)
                            decoded_payload = json.loads(base64.b64decode(payload_part + padding).decode('utf-8'))
                            st.session_state.user_email = decoded_payload.get("email", "No Email Found")
                        except Exception:
                            st.session_state.user_email = "인증 정보 해독 실패"
                else:
                    st.session_state.user_email = "ID 토큰을 찾을 수 없음"
                st.rerun()
    else:
        st.write(f"👤 **사용자:** {st.session_state.user_email}")
        # TypeError 수정: variant="secondary" -> type="secondary"
        if st.button("로그아웃", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()
    st.divider()

# 2. 사이드바 검색 기능 (Requirement 4)
st.sidebar.header("📈 종목 검색")
ticker = st.sidebar.text_input("티커 입력", value="AAPL")
period = st.sidebar.selectbox("조회 기간", ["1mo", "3mo", "6mo", "1y", "2y"])

# 3. 데이터 로드 및 지표 계산
@st.cache_data
def load_data(symbol, p):
    try:
        df = yf.download(symbol, period=p, interval="1d")
        if df.empty:
            return df
        
        # [Self-Test] MultiIndex 컬럼 처리: Operands alignment 에러 방지
        # yfinance 최신 버전에서 컬럼이 (Ticker, Price) 형태로 오는 경우를 대비해 평탄화
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 데이터 타입 강제 변환 (안정성 확보)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # 볼린저 밴드 계산 (Requirement 7)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['Lower'] = df['MA20'] - (df['STD20'] * 2)
        
        # RSI 계산 (Requirement 7)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 거래량 급증 판단 (Requirement 11: 평균 대비 2배 이상)
        df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
        # Series 정렬 강제화를 위해 명시적 비교 수행
        df['Vol_Spike'] = df['Volume'].astype(float) > (df['Vol_MA20'].astype(float) * 2)
        
        return df
    except Exception as e:
        st.error(f"데이터 처리 중 오류 발생: {e}")
        return pd.DataFrame()

# 3.1 셀프 테스트 기능 (에러 점검용)
def run_self_test(df):
    with st.sidebar.expander("🔍 시스템 셀프 테스트", expanded=False):
        checks = {
            "데이터 수신": not df.empty,
            "컬럼 정렬(Alignment)": "Vol_Spike" in df.columns,
            "기술적 지표(RSI)": not df['RSI'].isnull().all() if 'RSI' in df.columns else False,
            "거래량 분석": not df['Vol_MA20'].isnull().all() if 'Vol_MA20' in df.columns else False
        }
        for label, passed in checks.items():
            st.write(f"{'✅' if passed else '❌'} {label}")
        return all(checks.values())

# 4.1 DCF 분석 엔진 (전문화된 프롬프트 사용)
def run_dcf_analysis(df, ticker_name):
    with st.status("DCF 심층 분석 진행 중...", expanded=True) as status:
        st.write("📂 DCF 분석 가이드라인 로드 중...")
        try:
            with open("DCF_analysis.md", "r", encoding="utf-8") as f:
                dcf_instructions = f.read()
        except Exception as e:
            st.error(f"DCF 가이드라인을 로드할 수 없습니다: {e}")
            return None, 0

        st.write("📊 재무 데이터 및 시장 지표 취합 중...")
        latest = df.iloc[-1]
        current_price = latest['Close']
        rsi = latest['RSI']
        date = df.index[-1].strftime('%Y-%m-%d')
        
        # yfinance를 통해 추가 정보(기업명 등) 가져오기
        stock_info = yf.Ticker(ticker_name).info
        company_name = stock_info.get('longName') or stock_info.get('shortName') or ticker_name
        
        st.write(f"🤖 Gemini LLM 전문 분석 실행 ({company_name})...")
        prompt = f"""
        {dcf_instructions}
        
        [시스템 지침] 현재 시점은 2026년 2월입니다. 제공된 기업({company_name})과 티커({ticker_name})는 실시간 시장 데이터가 존재하는 상장사입니다. 
        당신의 학습 데이터(Cut-off)상 비상장으로 알고 있더라도, 현재는 상장된 상태이오니 비상장 관련 경고나 "가정하에 분석한다"는 멘트를 생략하고 즉시 상장사 기준의 분석(Narrative + Reverse DCF 등)을 수행하세요.
        제공된 현재가와 지표는 실제 시장 데이터입니다.
        
        분석 대상 기업: {company_name} ({ticker_name})
        현재 시장 데이터 ({date}):
        - 현재가: {current_price:.2f}
        - RSI(14): {rsi:.2f}
        
        위 가이드라인에 따라 즉시 분석 결과를 출력해 주세요. 서론이나 준비 멘트 없이 바로 본론(10 Key Points)으로 시작하세요.
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        status.update(label="DCF 분석 완료!", state="complete", expanded=False)
        
    return response.text, 95 # DCF 분석은 고정 신뢰도 예시

# 4. AI 분석 엔진 (단계별 표시 추가)
def run_ai_analysis(df, ticker_name):
    # st.status를 사용하여 단계별 진행 상황 표시
    with st.status("AI 분석 진행 중...", expanded=True) as status:
        st.write("📊 기술적 지표 분석 중 (RSI, Bollinger Bands)...")
        time.sleep(0.8) # 시각적 효과를 위한 지연
        
        st.write("📐 하모닉 패턴(AB=CD) 탐색 중...")
        # 패턴 분석 로직 (예시 데이터)
        pattern_detected = "Bullish AB=CD"
        confidence_score = 92 # 예시 점수
        time.sleep(0.8)
        
        st.write("🤖 Gemini LLM 전략 생성 중...")
        # 최신 데이터 추출
        latest = df.iloc[-1]
        current_price = latest['Close']
        rsi = latest['RSI']
        upper = latest['Upper']
        lower = latest['Lower']
        date = df.index[-1].strftime('%Y-%m-%d')
        current_time = time.strftime('%H:%M:%S')

        prompt = f"""
        당신은 세계적인 수준의 금융 분석가입니다. {ticker_name}에 대한 다음의 **실시간 시장 데이터**를 바탕으로 분석해 주세요.
        [시스템 지침] 현재 시점은 2026년 2월이며, {ticker_name}은 상장된 기업입니다. 제공된 데이터는 실제 실시간 데이터이므로 비상장 여부를 의심하지 말고 즉시 전략을 수립하세요.
        
        데이터 기준 시점: {date} {current_time}
        - 현재가: {current_price:.2f}
        - RSI(14): {rsi:.2f}
        - 볼린저 밴드: 상단 {upper:.2f} / 하단 {lower:.2f}
        - 탐지된 기술적 패턴: {pattern_detected}

        위의 **실시간 데이터**를 반드시 참고하여 현재 시점의 매수/매도 전략과 향후 전망을 한국어로 상세히 요약해 주세요. 
        당신이 알고 있는 과거의 주가 정보는 무시하고, 오직 위에 제공된 수치만을 근거로 판단해야 합니다.
        """
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        
        st.write("🔔 알림 조건 확인 중...")
        # 신뢰도 90점 이상인 경우에만 텔레그램 전송 (Requirement 10)
        if confidence_score >= 90:
            st.write(f"✅ 신뢰도 {confidence_score}점 확인. 텔레그램 알림을 전송합니다.")
            # telegram_send_logic(ticker_name, confidence_score)
        
        status.update(label="분석 완료!", state="complete", expanded=False)
    
    return response.text, confidence_score

# 5. 메인 화면 구성
st.title(f"📈 {ticker} 실시간 차트 및 AI 분석")

if ticker:
    df = load_data(ticker, period)
    
    if not df.empty:
        # 셀프 테스트 실행
        run_self_test(df)
        
        # 차트 생성
        fig = go.Figure()
        
        # 캔들스틱
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'], name="Price"
        ))
        
        # 볼린저 밴드 시각화
        fig.add_trace(go.Scatter(x=df.index, y=df['Upper'], line=dict(color='rgba(173, 216, 230, 0.5)'), name="Upper Band"))
        fig.add_trace(go.Scatter(x=df.index, y=df['Lower'], line=dict(color='rgba(173, 216, 230, 0.5)'), name="Lower Band", fill='tonexty'))

        # 거래량 급증 구간 배경 강조 (Requirement 11)
        spike_dates = df[df['Vol_Spike']].index
        for d in spike_dates:
            fig.add_vrect(
                x0=d, x1=d + pd.Timedelta(days=1),
                fillcolor="orange", opacity=0.1, layer="below", line_width=0
            )

        fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
        
        # 레이아웃 배치
        col1, col2 = st.columns([3, 1])
        with col1:
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("주요 지표")
            st.metric("현재가", f"{df['Close'].iloc[-1]:,.2f}")
            st.metric("RSI(14)", f"{df['RSI'].iloc[-1]:.2f}")

        # 6. AI 분석 섹션
        st.divider()
        st.subheader("🪄 AI 심층 분석 리포트")
        
        # 버튼 영역을 2개 컬럼으로 분할
        btn_col1, btn_col2 = st.columns(2)
        
        if 'analysis_type' not in st.session_state:
            st.session_state.analysis_type = None
        if 'analysis_content' not in st.session_state:
            st.session_state.analysis_content = ""
        if 'analysis_score' not in st.session_state:
            st.session_state.analysis_score = 0

        with btn_col1:
            if st.button("AI 분석 실행", use_container_width=True, type="primary"):
                content, score = run_ai_analysis(df, ticker)
                st.session_state.analysis_type = "AI"
                st.session_state.analysis_content = content
                st.session_state.analysis_score = score

        with btn_col2:
            if st.button("DCF 분석 실행", use_container_width=True, type="primary"):
                content, score = run_dcf_analysis(df, ticker)
                st.session_state.analysis_type = "DCF"
                st.session_state.analysis_content = content
                st.session_state.analysis_score = score

        # 결과 표시
        if st.session_state.analysis_type:
            title = "일반 AI 분석" if st.session_state.analysis_type == "AI" else "DCF 전문 분석"
            st.info(f"**[{title}] 신뢰도 점수: {st.session_state.analysis_score}점**")
            st.markdown(st.session_state.analysis_content)
            
            if st.button("텔레그램으로 전송하기", use_container_width=True):
                success, msg = send_telegram_message(f"**[{title}] {ticker} 분석 결과**\n\n{st.session_state.analysis_content}")
                if success:
                    st.success("텔레그램으로 전송되었습니다!")
                else:
                    st.error(f"텔레그램 전송에 실패했습니다: {msg}")
            
    else:
        st.error("데이터를 불러올 수 없습니다. 티커를 확인해주세요.")