import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import json
import datetime

# ==========================================
# [설정] 페이지 기본 설정
# ==========================================
st.set_page_config(page_title="금융 인사이트 AI Pro", page_icon="📈", layout="wide")

# ==========================================
# [함수] 구글 시트 연결 및 데이터 관리
# ==========================================
def get_sheet_client():
    # secrets.toml 파일이 없거나 설정이 잘못되면 여기서 에러가 발생합니다.
    if "gcp_service_account" not in st.secrets:
        st.error("Secrets 설정(gcp_service_account)이 누락되었습니다.")
        return None
        
    json_creds = dict(st.secrets["gcp_service_account"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, scope)
    client = gspread.authorize(creds)
    return client

def check_and_update_headers(sheet):
    """전문가 추천 필수 컬럼이 없으면 자동으로 추가"""
    required_headers = ['제목', '채널명', '게시일', '영상URL', '조회수', '카테고리', '핵심주제', '핵심주장', '요약', '시사점']
    try:
        current_headers = sheet.row_values(1)
    except:
        current_headers = []
        
    if not current_headers:
        sheet.append_row(required_headers)
        return required_headers
    
    missing_cols = [col for col in required_headers if col not in current_headers]
    if missing_cols:
        # 컬럼 추가 공간 확보
        if len(current_headers) + len(missing_cols) > sheet.col_count:
            sheet.resize(cols=len(current_headers) + len(missing_cols) + 5)
        
        start_col_idx = len(current_headers) + 1
        for i, col_name in enumerate(missing_cols):
            sheet.update_cell(1, start_col_idx + i, col_name)
        return current_headers + missing_cols
        
    return current_headers

@st.cache_data(ttl=600)
def load_data():
    client = get_sheet_client()
    if not client: return pd.DataFrame()
    
    try:
        sheet = client.open("Youtube_Test_Local").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 데이터프레임이 비어있거나 필수 컬럼이 없는 경우 처리
        expected_cols = ['제목', '채널명', '게시일', '영상URL', '조회수', '카테고리', '핵심주제', '요약', '시사점']
        for col in expected_cols:
            if col not in df.columns:
                df[col] = "" 
        df = df.fillna("")
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

def append_data_to_sheet(json_data):
    client = get_sheet_client()
    if not client: return False, "구글 시트 연결 실패"
    
    try:
        sheet = client.open("Youtube_Test_Local").sheet1
        current_headers = check_and_update_headers(sheet)
        
        if isinstance(json_data, dict):
            items = [json_data]
        elif isinstance(json_data, list):
            items = json_data
        else:
            return False, "JSON 형식이 올바르지 않습니다."

        rows_to_append = []
        for item in items:
            row = []
            for header in current_headers:
                row.append(str(item.get(header, "")))
            rows_to_append.append(row)
            
        sheet.append_rows(rows_to_append)
        return True, f"{len(items)}건 저장 완료! DB 헤더도 최신화되었습니다."
    except Exception as e:
        return False, f"오류 발생: {e}"

# ==========================================
# [함수] Gemini API
# ==========================================
def ask_gemini(query, context, mode="analysis"):
    try:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        if mode == "analysis":
            prompt = f"""
            당신은 수석 금융 투자 전략가입니다 (기준일: {today}).
            아래 [분석 데이터]를 기반으로 질문에 답하세요.
            
            [분석 데이터]
            {context}
            [질문]
            {query}
            
            [지침]
            1. '게시일'을 확인하여 정보의 최신성을 먼저 언급하세요.
            2. 여러 자료를 종합하여 명확한 투자 포지션(매수/매도/관망)을 제안하세요.
            """
        elif mode == "critique":
            prompt = f"""
            당신은 '금융 리스크 관리자'입니다. 
            아래 AI 답변을 검토하고 냉정한 비평 리포트를 작성하세요.

            [사용자 질문]
            {query}
            [AI 답변]
            {context}

            [작성 양식]
            1. 🚨 **리스크 경고:** 답변에서 간과한 경제 변수(금리, 환율 등)
            2. 📉 **데이터 신뢰도:** 정보가 너무 오래되었는지 여부
            3. ⚖️ **최종 판단:** '신뢰', '주의', '위험' 중 하나 선택
            """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 오류: {e}"

# ==========================================
# [UI] 화면 구성 시작
# ==========================================
st.title("📈 금융 인사이트 AI Pro")

# [확인용] 새 버전이 적용되었는지 알려주는 알림창 (실행되면 뜹니다)
st.success("✅ 시스템 업데이트 완료: 수동 입력 및 평가 기능이 활성화된 V3.1 버전입니다.")

# 데이터 로드 (가장 먼저 실행)
df = load_data()

# ------------------------------------------------------------------
# [1] 사이드바: 수동 DB 저장 (Expander 제거하여 항상 노출)
# ------------------------------------------------------------------
with st.sidebar:
    # 제목이 바뀌었는지 확인해주세요. (이전버전: 수집된 영상 -> 현재: 데이터 제어 센터)
    st.title("🗂️ 데이터 제어 센터")
    
    st.markdown("### 📝 데이터 수동 입력")
    st.info("ChatGPT가 만든 JSON을 아래에 붙여넣으세요.")
    
    # [수정] expander 제거, 직접 노출
    json_input = st.text_area("JSON 입력창", height=200, placeholder='[{"제목": "...", "게시일": "2024-01-01"}]', key="json_input_area_v3")
    
    if st.button("💾 DB에 저장하기 (클릭)", key="save_btn_v3", type="primary", use_container_width=True):
        if not json_input.strip():
            st.warning("데이터가 비어있습니다.")
        else:
            try:
                parsed_json = json.loads(json_input)
                success, msg = append_data_to_sheet(parsed_json)
                if success:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(msg)
            except json.JSONDecodeError:
                st.error("형식이 잘못되었습니다. 올바른 JSON을 입력하세요.")

    st.divider()
    
    # 데이터 목록 표시
    if not df.empty and '제목' in df.columns:
        st.caption(f"현재 DB 데이터: {len(df)}건")
        cols_to_show = ['제목']
        if '게시일' in df.columns: cols_to_show.append('게시일')
        
        display_df = df[cols_to_show].copy()
        display_df.insert(0, 'No', range(1, len(display_df) + 1))
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    if st.button("🔄 새로고침", key="refresh_btn_v3"):
        st.cache_data.clear()
        st.rerun()

# ------------------------------------------------------------------
# [2] 메인 채팅 인터페이스
# ------------------------------------------------------------------

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "안녕하세요! 어떤 투자 정보가 궁금하신가요?"}]

# 채팅 기록 출력
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# ------------------------------------------------------------------
# [3] 답변 평가 (AI 비평) 버튼
# 채팅 기록 루프가 끝난 직후, 입력창 바로 위에 '컨테이너'로 고정 표시
# ------------------------------------------------------------------
# 조건: 대화 기록이 있고, 마지막 메시지가 AI(assistant)인 경우
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    # 첫 인사말("안녕하세요!")에는 평가 버튼을 띄우지 않음
    if len(st.session_state.messages) > 1: 
        st.markdown("---") # 구분선 추가
        
        # 눈에 띄는 빨간색 박스 안에 배치
        with st.container(border=True):
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.write("### 🧐 답변 검증이 필요하신가요?")
                st.caption("AI 리스크 관리자가 이 답변의 위험 요소를 분석해 드립니다.")
            with col2:
                # 버튼 클릭 시 동작
                if st.button("🚩 리스크 비평 보기", key="critique_btn_v3", type="secondary", use_container_width=True):
                    # 마지막 질문과 답변 가져오기
                    last_msg_content = st.session_state.messages[-1]["content"]
                    last_user_query = st.session_state.messages[-2]["content"]
                    
                    with st.spinner("🔍 외부 지식과 대조하며 팩트 체크 중..."):
                        critique = ask_gemini(last_user_query, last_msg_content, mode="critique")
                        
                        # 비평 내용을 채팅창에 추가
                        st.session_state.messages.append({"role": "assistant", "content": f"📝 **[전문가 비평 리포트]**\n\n{critique}"})
                        st.rerun() # 화면 갱신하여 즉시 표시

# ------------------------------------------------------------------
# [4] 사용자 입력창 (항상 하단 고정)
# ------------------------------------------------------------------
if prompt := st.chat_input("질문 예: 삼성전자 전망은? (최근 데이터 기준)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun() # 입력 즉시 화면 갱신

# ------------------------------------------------------------------
# [5] 답변 생성 로직 (Rerun 후 실행됨)
# ------------------------------------------------------------------
# 마지막 메시지가 사용자일 때만 실행 (AI 답변 생성)
if st.session_state.messages[-1]["role"] == "user":
    user_query = st.session_state.messages[-1]["content"]
    
    # 검색 로직
    search_cols = ['제목', '핵심주제', '요약', '카테고리']
    valid_cols = [col for col in search_cols if col in df.columns]
    
    context_text = ""
    if not df.empty and valid_cols:
        mask = df[valid_cols].astype(str).apply(lambda x: x.str.contains(user_query, case=False).any(), axis=1)
        filtered_df = df[mask]
        target_df = filtered_df if not filtered_df.empty else df.tail(5)
        
        for idx, row in target_df.iterrows():
            context_text += f"- 제목: {row.get('제목')} (날짜: {row.get('게시일')})\n- 요약: {row.get('요약')}\n- 시사점: {row.get('시사점')}\n\n"
    else:
        context_text = "관련 데이터가 없습니다."

    with st.chat_message("assistant"):
        with st.spinner("데이터 분석 중..."):
            response = ask_gemini(user_query, context_text, mode="analysis")
            st.write(response)
            
            # 답변을 세션에 추가
            st.session_state.messages.append({"role": "assistant", "content": response})
            # 답변이 추가되었으므로 다시 Rerun하여 [3]번의 평가 버튼이 보이게 함
            st.rerun()
