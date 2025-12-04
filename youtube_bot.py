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
# [확인용] 내가 실행시킨 코드가 맞는지 확인하는 문구
# ==========================================
print("\n" + "="*50)
print("🚀 [사용자님 확인용] 단일 채널 테스트 봇 가동!")
print("🎯 타겟 채널: 오직 '김영익의 경제스쿨' 하나만 검사합니다.")
print("="*50 + "\n")

# ==========================================
# [설정] 한국 시간 & 날짜 필터 & 채널
# ==========================================
KST = timezone(timedelta(hours=9))
FILTER_DAYS = 3

# ★ 여기 딱 하나만 남겼습니다 ★
TARGET_CHANNELS = {
    "김영익의 경제스쿨" : "UCQIyAcoLsO3L0RMFQk7YMYA"
}

SYSTEM_PROMPT = """
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
  "full_summary": "전체 내용 상세 요약"
}
"""

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
        video_date_kst = video_date_utc.astimezone(KST).strftime("%Y-%m-%d")
        
        if delta.days <= FILTER_DAYS:
            return True, video_date_kst
        else:
            return False, video_date_kst
    except:
        return True, datetime.now(KST).strftime("%Y-%m-%d")

def run_bot():
    sheet = connect_google_sheet()
    if not sheet: return

    existing_ids = get_existing_video_ids(sheet)
    print(f"📚 기존 데이터 {len(existing_ids)}개 확인됨")

    for channel_name, channel_id in TARGET_CHANNELS.items():
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(rss_url)
        
        print(f"📡 스캔 중: {channel_name} (ID: {channel_id})")
        print(f"   -> 유튜브에서 가져온 최신 영상 개수: {len(feed.entries)}개")
        
        for entry in feed.entries:
            video_id = entry.yt_videoid
            video_url = entry.link
            video_title = entry.title
            
            if video_id in existing_ids:
                continue 

            is_recent, video_date = is_recent_video(entry)
            if not is_recent:
                continue

            print(f"   ✨ [신규 발견] {video_title} ({video_date}) -> 분석 시작")
            
            result = analyze_video(video_url)
            
            if result:
                key_args = "\n- ".join(result.get("key_arguments", []))
                if key_args: key_args = "- " + key_args
                evidence = "\n- ".join(result.get("evidence", []))
                if evidence: evidence = "- " + evidence

                row_data = [
                    datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
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
                print(f"   ✅ 구글 시트 저장 완료!")
                existing_ids.append(video_id)
                time.sleep(5)

if __name__ == "__main__":
    run_bot()
