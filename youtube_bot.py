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
    json_creds = dict(st.secrets["gcp_service_account"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, scope)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=600)
def load_data():
    try:
        client = get_sheet_client()
        sheet = client.open("Youtube_Test_Local").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 빈 값 처리 및 필수 컬럼 보정 (데이터가 없을 경우 에러 방지)
        expected_cols = ['제목', '채널명', '게시일', '영상URL', '조회수', '카테고리', '핵심주제', '요약', '시사점']
        for col in expected_cols:
            if col not in df.columns:
                df[col] = "" # 없는 컬럼은 빈 값으로 생성
                
        df = df.fillna("")
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

def append_data_to_sheet(json_data):
    try:
        client = get_sheet_client()
        sheet = client.open("Youtube_Test_Local").sheet1
        
        if isinstance(json_data, dict):
            items = [json_data]
        elif isinstance(json_data, list):
            items = json_data
        else:
            return False, "JSON 형식이 올바르지 않습니다."

        headers = sheet.row_values(1)
        if not headers:
            return False, "구글 시트에 헤더가 없습니다. (권장 헤더: 제목, 채널명, 게시일, 영상URL, 조회수, 카테고리, 핵심주제, 요약, 시사점)"

        rows_to_append = []
        for item in items:
            row = []
            for header in headers:
                row.append(item.get(header, ""))
            rows_to_append.append(row)
            
        sheet.append_rows(rows_to_append)
        return True, f"{len(items)}건의 데이터가 성공적으로 추가되었습니다."
    except Exception as e:
        return False, f"데이터 추가 중 오류 발생: {e}"

# ==========================================
# [함수] Gemini API 호출
# ==========================================
def ask_gemini(query, context, mode="analysis"):
    try:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        if mode == "analysis":
            # [전문가 반영] 게시일(Date)과 출처 신뢰도 강조
            prompt = f"""
            당신은 수석 금융 투자 전략가입니다. 오늘 날짜는 {today}입니다.
            아래 [분석 리포트 데이터]를 바탕으로 사용자의 질문에 답하세요.

            [분석 리포트 데이터]
            {context}

            [사용자 질문]
            {query}

            [답변 가이드라인]
            1. **시의성 고려:** 각 정보의 '게시일'을 반드시 확인하여, 너무 오래된(6개월 이상) 정보는 현재 상황과 다를 수 있음을 명시하세요.
            2. **논리적 종합:** 단순 나열이 아니라, 여러 채널의 의견을 종합하여 결론을 내세요.
            3. **명확한 출처:** "A채널(2024-05-20)에 따르면..."과 같이 출처와 시점을 함께 언급하세요.
            4. **투자 조언:** 데이터에 기반한 구체적인 행동(매수/매도/관망 등)을 제안하세요.
            """
        
        elif mode == "critique":
            # [전문가 반영] 비평 시 '오래된 정보' 리스크 체크 추가
            prompt = f"""
            당신은 까다로운 금융 리스크 관리자입니다. 오늘 날짜는 {today}입니다.
            사용자 질문과 그에 대한 AI 답변(DB 기반)을 보고, 비판적인 리포트를 작성하세요.

            [사용자 질문]
            {query}

            [AI 답변]
            {context}

            [평가 포인트]
            1. **데이터 시의성:** 답변에 사용된 데이터가 너무 오래되지 않았는지(Outdated) 확인하고 경고하세요.
            2. **거시경제 누락:** 현재 시점의 주요 경제 지표(금리, 환율 등)와 답변이 배치되지 않는지 확인하세요.
            3. **편향성 체크:** 답변이 특정 유튜버의 낙관론/비관론에만 쏠려있지 않은지 지적하세요.
            4. **총평:** 이 정보를 믿고 투자해도 되는지 '주의/신뢰/보류' 중 하나로 등급을 매기세요.
            """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 처리 중 오류가 발생했습니다: {e}"

# ==========================================
# [UI] 화면 구성
# ==========================================
st.title("📈 금융 인사이트 AI Pro")
st.caption("🚀 전문가 설계 반영: 시계열 분석 및 데이터 검증 시스템")

df = load_data()

# ==========================================
# [사이드바] 데이터 관리 시스템
# ==========================================
with st.sidebar:
    st.header(f"🗂️ 금융 데이터베이스 ({len(df)}건)")
    
    # 탭으로 기능 분리
    tab1, tab2 = st.tabs(["📝 데이터 추가", "⚙️ 설정 가이드"])
    
    with tab1:
        with st.expander("JSON 데이터 입력", expanded=True):
            st.info("💡 아래 프롬프트를 복사하여 ChatGPT/Gemini에게 영상 요약을 요청하세요.")
            
            # [전문가 반영] 최적화된 프롬프트 제공
            prompt_template = """
당신은 금융 데이터 전문가입니다. 영상을 보고 아래 JSON 포맷으로 1개의 데이터를 생성하세요.
{
  "제목": "영상 제목",
  "채널명": "채널 이름",
  "게시일": "YYYY-MM-DD",
  "영상URL": "https://youtu.be/...",
  "카테고리": "주식/부동산/코인/거시경제 중 택1",
  "조회수": "10000",
  "핵심주제": "메인 토픽",
  "핵심주장": "결론 한 문장",
  "요약": "3줄 요약",
  "시사점": "투자 액션 플랜"
}
            """
            st.code(prompt_template, language="text")
            
            st.markdown("---")
            st.caption("👇 생성된 JSON을 여기에 붙여넣으세요")
            json_input = st.text_area("JSON 입력창", height=200, placeholder='[{"제목": "...", ...}]')
            
            if st.button("💾 DB에 저장"):
                if not json_input.strip():
                    st.error("내용을 입력해주세요.")
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
                        st.error("JSON 형식이 올바르지 않습니다.")

    with tab2:
        st.markdown("""
        **[구글 시트 필수 헤더]**
        데이터가 정상적으로 저장되려면 구글 시트 1행에 아래 헤더가 있어야 합니다.
        
        `제목`, `채널명`, `게시일`, `영상URL`, `카테고리`, `조회수`, `핵심주제`, `핵심주장`, `요약`, `시사점`
        """)

    # 데이터 목록 표시
    if '제목' in df.columns:
        st.markdown("---")
        st.subheader("데이터 미리보기")
        display_df = df[['제목']].copy()
        
        # [전문가 반영] 중요한 정보(게시일, 카테고리)가 있다면 같이 표시
        if '게시일' in df.columns:
            display_df['게시일'] = df['게시일']
        if '카테고리' in df.columns:
            display_df['카테고리'] = df['카테고리']
            
        display_df.insert(0, 'No', range(1, len(display_df) + 1))
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# [메인] 채팅 인터페이스
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "안녕하세요! 투자 전략가 AI입니다. 시장 분석을 도와드릴까요?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("질문 예: 삼성전자 전망은? (최근 1개월 데이터 기준)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 검색 로직
    search_cols = ['제목', '핵심주제', '핵심주장', '근거', '요약', '태그', '시사점', '카테고리']
    valid_cols = [col for col in search_cols if col in df.columns]
    
    context_text = ""
    if not df.empty and valid_cols:
        mask = df[valid_cols].astype(str).apply(lambda x: x.str.contains(prompt, case=False).any(), axis=1)
        filtered_df = df[mask]
        
        target_df = filtered_df if not filtered_df.empty else df.tail(5)
        msg_prefix = f"🔍 **{len(filtered_df)}개**의 관련 데이터" if not filtered_df.empty else "💡 검색 결과가 없어 **최근 데이터 5개**"
        
        # [전문가 반영] 분석 컨텍스트에 날짜/카테고리/URL 등 상세 정보 포함
        for idx, row in target_df.iterrows():
            title = row.get('제목', '제목 없음')
            date = row.get('게시일', '날짜 미상')
            channel = row.get('채널명', '채널 미상')
            category = row.get('카테고리', '')
            url = row.get('영상URL', '')
            summary = row.get('요약', '')
            implication = row.get('시사점', '')
            
            context_text += f"""
            --- [데이터 {idx}] ---
            * 제목: {title}
            * 출처: {channel} (게시일: {date})
            * 카테고리: {category}
            * 내용 요약: {summary}
            * 투자 시사점: {implication}
            * URL: {url}
            --------------------
            """
    else:
        msg_prefix = "⚠️ 데이터베이스가 비어있거나 로드되지 않았습니다."

    with st.chat_message("assistant"):
        st.info(f"{msg_prefix}를 기반으로 분석합니다.")
        with st.spinner("전문가 관점으로 분석 중..."):
            response = ask_gemini(prompt, context_text, mode="analysis")
            st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            st.session_state.last_response = response
            st.session_state.last_query = prompt

# [기능] AI 비평 및 리스크 검증
if "last_response" in st.session_state:
    st.divider()
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        st.caption("💡 AI의 분석이 너무 낙관적이거나 편향되었을 수 있습니다.")
    with col2:
        if st.button("⚖️ 리스크 검증 (AI 비평)"):
            with st.spinner("외부 지식(금리, 환율 등)과 교차 검증 중..."):
                critique = ask_gemini(st.session_state.last_query, st.session_state.last_response, mode="critique")
                
                with st.chat_message("assistant", avatar="⚖️"):
                    st.markdown("### ⚖️ 리스크 검증 리포트")
                    st.markdown(critique)
                    st.session_state.messages.append({"role": "assistant", "content": f"⚖️ [리스크 검증 리포트]\n{critique}"})
