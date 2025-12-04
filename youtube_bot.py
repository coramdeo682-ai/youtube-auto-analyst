import os
import json
import time
from datetime import datetime, timedelta, timezone
from time import mktime
import feedparser
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import pandas as pd

# ==========================================
# [설정 1] 한국 시간대(KST) 설정 & 날짜 필터
# ==========================================
KST = timezone(timedelta(hours=9))
FILTER_DAYS = 3  # 최근 3일 이내 영상만 수집 (오래된 영상 원천 차단)

# ==========================================
# [설정 2] 구독할 유튜브 채널 목록 (최신 확정판)
# ==========================================
TARGET_CHANNELS = {
    "김영익의 경제스쿨" : "UCQIyAcoLsO3L0RMFQk7YMYA",
    "경제 읽어주는 남자(김광석TV)" : "UC3pfEoxaRDT6hvZZjpHu7Tg",
    "내일은 투자왕 - 김단테" : "UCKTMvIu9a4VGSrpWy-8bUrQ",
    "박종훈의 지식한방" : "UCOB62fKRT7b73X7tRxMuN2g",
    "월가아재의 과학적 투자" : "UCpqD9_OJNtF6suPpi6mOQCQ",
    "전인구경제연구소" : "UC3uzeWjN8v_ItMWhxILvuvQ",
    "존리의 부자학교" : "UCXWOlSe2GHTev8QZhY_gMPg", 
    "트래블제이(Travel J)주식투자와 10년 세계탐방" : "UCM0iG9ePKMIuGxUFBObgK9A",  
    "할 수 있다! 알고 투자" : "UCSWPuzlD337Y6VBkyFPwT8g",
    "홍춘욱의 경제강의노트" : "UCmNbuxmvRVv9OcdAO0cpLnw"
}

# ==========================================
# [설정 3] 프롬프트
# ==========================================
SYSTEM_PROMPT = """
지금부터 내가 유튜브 링크를 주면, 해당 영상의 내용을 분석해서 아래의 JSON 포맷으로 출력해 줘. 
다른 말은 하지 말고 오직 JSON 코드만 출력해. (코드 블록 안에 넣어서)

[분석 지침]
1. 'key_arguments'와 'evidence'는 짝을 이루어 구체적으로 작성할 것.
2. 수치(%, 금액, 날짜)가 있다면 반드시 포함할 것.
3. 투자자 관점에서 실질적인 도움이 되는 정보를 추출할 것.

[JSON 포맷]
{
  "video_id": "영상ID",
  "url": "영상 전체 URL",
  "title": "영상 제목",
  "channel_name": "채널명",
  "published_at": "업로드 날짜 (YYYY-MM-DD)",
  "main_topic": "핵심 주제 (1문장)",
  "key_arguments": ["핵심 주장 1", "핵심 주장 2", "핵심 주장 3"],
  "evidence": ["주장 1에 대한 근거(수치/팩트)", "주장 2에 대한 근거", "주장 3에 대한 근거"],
  "implications": "이 내용이 주는 시사점 및 투자 인사이트 (상세 기술)",
  "validity_check": "논리적 타당성 및 비판적 검토",
  "sentiment": "긍정/부정/중립",
  "tags": "키워드1, 키워드2, 키워드3",
  "full_summary": "전체 내용 상세 요약 (서론-본론-결론)"
}
"""

# ==========================================
# [핵심 로직]
# ==========================================

def connect_google_sheet():
    try:
        json_creds = json.loads(os.environ['GCP_CREDENTIALS_JSON'])
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Youtube_Data_Store").sheet1 
        return sheet
    except Exception as e:
        print(f"🚨 구글 시트 연결 실패: {e}")
        return None

def get_existing_video_ids(sheet):
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty or '영상ID' not in df.columns:
            return []
        return df['영상ID'].astype(str).tolist()
    except:
        return []

def analyze_video(video_url):
    try:
        api_key = os.environ['GOOGLE_API_KEY']
        genai.configure(api_key=api_key)
        # 1.5 flash 모델 사용
        model = genai.GenerativeModel('gemini-2.5-flash') 
        
        full_prompt = f"{SYSTEM_PROMPT}\n\n[분석할 영상 링크]: {video_url}"
        response = model.generate_content(full_prompt)
        
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        return json.loads(text)
    except Exception as e:
        print(f"❌ Gemini 분석 실패 ({video_url}): {e}")
        return None

def is_recent_video(entry):
    try:
        published_time = entry.published_parsed
        video_date_utc = datetime.fromtimestamp(mktime(published_time), tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delta = now_utc - video_date_utc
        
        # 한국 시간 문자열 변환
        video_date_kst = video_date_utc.astimezone(KST).strftime("%Y-%m-%d")
        
        if delta.days <= FILTER_DAYS:
            return True, video_date_kst
        else:
            return False, video_date_kst
    except:
        return True, datetime.now(KST).strftime("%Y-%m-%d")

def run_bot():
    print(f"🚀 [NEW] 봇 실행 시작 (한국시간): {datetime.now(KST)}")
    print(f"📅 날짜 필터 적용 중: 최근 {FILTER_DAYS}일 이내 영상만 수집합니다.")
    
    sheet = connect_google_sheet()
    if not sheet: return

    existing_ids = get_existing_video_ids(sheet)
    print(f"📚 기존 데이터 {len(existing_ids)}개 로드 완료")

    new_videos_found = 0

    for channel_name, channel_id in TARGET_CHANNELS.items():
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(rss_url)
        
        print(f"📡 채널 스캔 중: {channel_name}")
        
        for entry in feed.entries:
            video_id = entry.yt_videoid
            video_url = entry.link
            video_title = entry.title
            
            if video_id in existing_ids:
                continue 

            # [날짜 필터링]
            is_recent, video_date = is_recent_video(entry)
            if not is_recent:
                # 오래된 영상은 무시
                continue

            print(f"   ✨ 신규 영상 발견! ({video_date}) 분석 시작... [{video_title}]")
            
            result = analyze_video(video_url)
            
            if result:
                key_args = "\n- ".join(result.get("key_arguments", []))
                if key_args: key_args = "- " + key_args
                evidence = "\n- ".join(result.get("evidence", []))
                if evidence: evidence = "- " + evidence

                # 한국 시간으로 수집일시 저장
                row_data = [
                    datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), # 여기가 핵심! (한국시간)
                    result.get("published_at", video_date),
                    result.get("video_id", video_id),
                    result.get("title", video_title),
                    result.get("channel_name", channel_name),
                    result.get("main_topic", ""),
                    key_args,
                    evidence,
                    result.get("implications", ""),
                    result.get("validity_check", ""),
                    result.get("sentiment", ""),
                    result.get("full_summary", ""),
                    result.get("tags", ""),
                    result.get("url", video_url)
                ]
                
                sheet.append_row(row_data)
                print(f"   ✅ 저장 완료!")
                existing_ids.append(video_id)
                new_videos_found += 1
                time.sleep(5)

    print(f"🏁 작업 종료. 총 {new_videos_found}개의 새 영상을 분석했습니다.")

if __name__ == "__main__":
    run_bot()
