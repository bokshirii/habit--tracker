# app.py
import os
import re
from datetime import datetime, timedelta

import requests
import pandas as pd
import streamlit as st

# OpenAI (official SDK)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="AI 습관 트래커", page_icon="📊", layout="wide")
st.title("📊 AI 습관 트래커")


# -----------------------------
# Sidebar: API Keys
# -----------------------------
with st.sidebar:
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    owm_key = st.text_input("OpenWeatherMap API Key", type="password", value=os.getenv("OPENWEATHERMAP_API_KEY", ""))
    st.caption("키는 로컬에서만 쓰이고, 서버에 저장하지 않도록 구성하는 걸 권장합니다.")


# -----------------------------
# Session state init (6-day demo)
# -----------------------------
def _init_demo_history():
    # 데모 6일: 달성률(%)용으로 habits_count만 저장
    base = datetime.now().date()
    demo = [
        {"date": (base - timedelta(days=6)).isoformat(), "habits_count": 2, "mood": 5},
        {"date": (base - timedelta(days=5)).isoformat(), "habits_count": 3, "mood": 6},
        {"date": (base - timedelta(days=4)).isoformat(), "habits_count": 1, "mood": 4},
        {"date": (base - timedelta(days=3)).isoformat(), "habits_count": 4, "mood": 7},
        {"date": (base - timedelta(days=2)).isoformat(), "habits_count": 3, "mood": 6},
        {"date": (base - timedelta(days=1)).isoformat(), "habits_count": 5, "mood": 8},
    ]
    return demo


if "history" not in st.session_state:
    st.session_state["history"] = _init_demo_history()


# -----------------------------
# APIs
# -----------------------------
def get_weather(city: str, api_key: str):
    """
    OpenWeatherMap 현재 날씨
    - 한국어(lang=kr), 섭씨(units=metric)
    - 실패 시 None
    """
    if not api_key:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": api_key, "units": "metric", "lang": "kr"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        return {
            "city": city,
            "temp": data.get("main", {}).get("temp"),
            "feels_like": data.get("main", {}).get("feels_like"),
            "humidity": data.get("main", {}).get("humidity"),
            "desc": (data.get("weather") or [{}])[0].get("description"),
        }
    except Exception:
        return None


def _breed_from_dog_ceo_url(image_url: str):
    # 예: https://images.dog.ceo/breeds/hound-afghan/n02088094_1003.jpg
    m = re.search(r"/breeds/([^/]+)/", image_url or "")
    if not m:
        return None
    slug = m.group(1)  # hound-afghan 또는 shiba 등
    parts = slug.split("-")
    # Dog CEO는 종-서브종 순서가 많음: "hound-afghan" -> Afghan Hound로 보기 좋게
    if len(parts) >= 2:
        main = parts[0]
        sub = " ".join(parts[1:])
        return f"{sub.title()} {main.title()}".strip()
    return parts[0].title()


def get_dog_image():
    """
    Dog CEO 랜덤 강아지
    - 실패 시 None
    """
    try:
        url = "https://dog.ceo/api/breeds/image/random"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "success":
            return None
        img_url = data.get("message")
        breed = _breed_from_dog_ceo_url(img_url) or "Unknown"
        return {"image_url": img_url, "breed": breed}
    except Exception:
        return None


def generate_report(
    habits_checked: dict,
    mood: int,
    weather: dict | None,
    dog: dict | None,
    coach_style: str,
    openai_api_key: str,
):
    """
    OpenAI에 습관+기분+날씨+강아지 품종 전달해서 리포트 생성
    - 모델: gpt-5-mini
    - 실패 시 None
    """
    if not openai_api_key or OpenAI is None:
        return None

    style_prompts = {
        "스파르타 코치": (
            "당신은 매우 엄격한 코치입니다. 돌려 말하지 말고, 짧고 직설적으로, "
            "핑계는 차단하고 실행만 강조하세요. 하지만 인신공격은 금지입니다."
        ),
        "따뜻한 멘토": (
            "당신은 따뜻한 멘토입니다. 다정하지만 구체적으로, 자책을 줄이고 "
            "실행 가능한 작은 다음 스텝을 제안하세요."
        ),
        "게임 마스터": (
            "당신은 RPG 게임 마스터입니다. 유저는 플레이어, 습관은 퀘스트입니다. "
            "세계관/레벨/보상/미션을 재미있게 구성하되 과장된 허풍은 금지입니다."
        ),
    }
    system_prompt = style_prompts.get(coach_style, style_prompts["따뜻한 멘토"])

    habits_done = [k for k, v in habits_checked.items() if v]
    habits_miss = [k for k, v in habits_checked.items() if not v]

    weather_text = "날씨 정보 없음"
    if weather:
        weather_text = (
            f"{weather.get('city')} / {weather.get('desc')} / "
            f"{weather.get('temp')}°C (체감 {weather.get('feels_like')}°C), 습도 {weather.get('humidity')}%"
        )

    dog_text = "강아지 정보 없음"
    if dog:
        dog_text = f"{dog.get('breed')}"

    user_prompt = f"""
[오늘 체크인]
- 완료한 습관: {", ".join(habits_done) if habits_done else "없음"}
- 미완료 습관: {", ".join(habits_miss) if habits_miss else "없음"}
- 기분(1~10): {mood}

[환경 정보]
- 날씨: {weather_text}
- 오늘의 강아지 품종: {dog_text}

아래 형식으로만 출력하세요(섹션 제목 포함):
1) 컨디션 등급: S/A/B/C/D (한 줄)
2) 습관 분석: (짧은 문단 + 핵심 bullet 3개)
3) 날씨 코멘트: (1~2문장)
4) 내일 미션: (체크박스 스타일로 3개: - [ ] ...)
5) 오늘의 한마디: (한 줄, 공유하고 싶게)
""".strip()

    try:
        client = OpenAI(api_key=openai_api_key)
        resp = client.responses.create(
            model="gpt-5-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        # SDK 편의 속성 우선, 없으면 안전하게 파싱
        text = getattr(resp, "output_text", None)
        if text:
            return text.strip()

        # fallback: output 배열에서 text 찾기
        out = getattr(resp, "output", []) or []
        chunks = []
        for item in out:
            for c in item.get("content", []) if isinstance(item, dict) else []:
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    chunks.append(c["text"])
        return "\n".join(chunks).strip() if chunks else None
    except Exception:
        return None


# -----------------------------
# Check-in UI
# -----------------------------
st.subheader("✅ 오늘의 습관 체크인")

habit_defs = [
    ("🌅", "기상 미션"),
    ("💧", "물 마시기"),
    ("📚", "공부/독서"),
    ("🏃", "운동하기"),
    ("😴", "수면"),
]

col_left, col_right = st.columns(2)
habits_checked = {}

for idx, (emoji, name) in enumerate(habit_defs):
    target_col = col_left if idx % 2 == 0 else col_right
    with target_col:
        habits_checked[name] = st.checkbox(f"{emoji} {name}", value=False, key=f"habit_{name}")

mood = st.slider("😊 오늘 기분은 어때요? (1~10)", min_value=1, max_value=10, value=6, step=1)

cities = [
    "Seoul",
    "Busan",
    "Incheon",
    "Daegu",
    "Daejeon",
    "Gwangju",
    "Ulsan",
    "Suwon",
    "Seongnam",
    "Jeju",
]
c1, c2 = st.columns([1, 1])
with c1:
    city = st.selectbox("🏙️ 도시 선택", cities, index=0)
with c2:
    coach_style = st.radio("🧠 코치 스타일", ["스파르타 코치", "따뜻한 멘토", "게임 마스터"], horizontal=True)

checked_count = sum(1 for v in habits_checked.values() if v)
achievement = int(round((checked_count / 5) * 100))


# -----------------------------
# Metrics
# -----------------------------
st.subheader("📈 오늘 요약")
m1, m2, m3 = st.columns(3)
m1.metric("달성률", f"{achievement}%")
m2.metric("달성 습관", f"{checked_count}/5")
m3.metric("기분", f"{mood}/10")


# -----------------------------
# 7-day chart (6 demo + today's current)
# -----------------------------
today = datetime.now().date().isoformat()
demo_history = st.session_state["history"]

# 최근 6개만 유지 (안정성)
demo_history = sorted(demo_history, key=lambda x: x["date"])[-6:]

chart_rows = demo_history + [{"date": today, "habits_count": checked_count, "mood": mood}]
df = pd.DataFrame(chart_rows)
df["achievement"] = (df["habits_count"] / 5.0) * 100

st.subheader("🗓️ 최근 7일 달성률")
st.bar_chart(df.set_index("date")["achievement"])


# -----------------------------
# Generate report button + display
# -----------------------------
st.divider()
st.subheader("🧾 AI 코치 리포트")

generate = st.button("컨디션 리포트 생성", type="primary")

if generate:
    # 오늘 기록 session_state에 저장 (중복 날짜면 업데이트)
    history = st.session_state["history"]
    history_map = {row["date"]: row for row in history}
    history_map[today] = {"date": today, "habits_count": checked_count, "mood": mood}
    # 오래된 것부터 정리해서 최대 30일 정도만 유지(가벼운 방어)
    merged = sorted(history_map.values(), key=lambda x: x["date"])[-30:]
    st.session_state["history"] = merged

    # External APIs
    weather = get_weather(city, owm_key)
    dog = get_dog_image()

    # Cards: weather + dog
    wcol, dcol = st.columns(2)

    with wcol:
        st.markdown("### 🌦️ 오늘의 날씨")
        if weather:
            st.info(
                f"**{weather.get('city')}**\n\n"
                f"- 상태: {weather.get('desc')}\n"
                f"- 기온: {weather.get('temp')}°C (체감 {weather.get('feels_like')}°C)\n"
                f"- 습도: {weather.get('humidity')}%"
            )
        else:
            st.warning("날씨 정보를 가져오지 못했습니다. (API Key/도시/네트워크 확인)")

    with dcol:
        st.markdown("### 🐶 오늘의 강아지")
        if dog and dog.get("image_url"):
            st.image(dog["image_url"], use_container_width=True)
            st.caption(f"품종(추정): {dog.get('breed', 'Unknown')}")
        else:
            st.warning("강아지 이미지를 가져오지 못했습니다.")

    # AI report
    st.markdown("### 🤖 코치 리포트")
    report = generate_report(
        habits_checked=habits_checked,
        mood=mood,
        weather=weather,
        dog=dog,
        coach_style=coach_style,
        openai_api_key=openai_key,
    )

    if report:
        st.success("리포트 생성 완료!")
        st.markdown(report)
    else:
        st.error("리포트 생성 실패. (OpenAI API Key/라이브러리 설치/네트워크 확인)")

    # Share text
    st.markdown("### 📋 공유용 텍스트")
    weather_short = (
        f"{weather.get('desc')} / {weather.get('temp')}°C" if weather else "날씨 정보 없음"
    )
    dog_short = (dog.get("breed") if dog else "강아지 정보 없음")

    share_text = f"""[AI 습관 트래커] {today}
- 달성률: {achievement}% ({checked_count}/5)
- 기분: {mood}/10
- 도시/날씨: {city} / {weather_short}
- 오늘의 강아지: {dog_short}

{report or "(리포트 생성 실패)"}
""".strip()

    st.code(share_text, language="text")


# -----------------------------
# Footer: API 안내
# -----------------------------
with st.expander("🧩 API 안내 / 문제 해결", expanded=False):
    st.markdown(
        """
- **OpenAI API Key**
  - OpenAI 플랫폼에서 발급한 키를 입력하세요.
  - 서버에 배포할 경우, 코드에 하드코딩하지 말고 환경변수/시크릿을 권장합니다.  
- **OpenWeatherMap API Key**
  - OpenWeatherMap에서 키를 발급받아 입력하세요.
  - 도시명이 영어로 들어갑니다(Seoul, Busan 등).  
- **Dog CEO**
  - 키 없이 무료로 랜덤 강아지 이미지를 제공합니다.
- **자주 나는 오류**
  - 날씨가 None: OWM 키/도시명/요금제/쿼터/네트워크 확인
  - OpenAI 호출 실패: 키 유효성, `pip install openai` 설치 여부, 네트워크 확인
"""
    )
