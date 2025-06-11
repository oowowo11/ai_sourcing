import os
import streamlit as st
import openai
import requests
import io
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import openpyxl
import urllib.parse
import time
from datetime import datetime

# 1) OpenAI 키
API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    st.error("🔑 OPENAI_API_KEY가 설정되지 않았습니다. Streamlit Secrets에 등록해주세요.")
    st.stop()

# 2. 엑셀 템플릿 파일명 (필요에 따라 경로 수정)
taobao_template = "123.xlsx"
rakuten_template = "123.xlsx"

def setup_driver(lang):
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("start-maximized")
    if lang == "zh-CN":
        options.add_argument("--lang=zh-CN")
    else:
        options.add_argument("--lang=ja-JP")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """ if lang == "zh-CN" else """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """
    })
    return driver

def generate_keywords(category, target, n, market):
    # system, prompt 구성은 그대로 둡니다.
    if market == "타오바오":
        system = "You are an expert in Chinese cross-border e-commerce trend analysis. Please respond in Korean."
        prompt = (
            f"Recommend {n} trending premium products in category '{category}' "
            f"for audience '{target}'. "
            "Provide each item as <Korean> – <Chinese>."
        )
    else:
        system = "You are an expert in Japanese e-commerce fashion trends. Please respond in Korean."
        prompt = (
            f"Recommend {n} popular product keywords for Rakuten Brand Avenue "
            f"in category '{category}', target '{target}'. "
            "Return each as (Korean, Japanese) lines."
        )

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o",
        "messages": [
            {"role":"system", "content": system},
            {"role":"user",   "content": prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.7
    }

    try:
        r = requests.post(url, headers=headers, json=data, timeout=60)
        r.raise_for_status()
        resp = r.json()
        text = resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        st.error("❗️ OpenAI 호출 중 오류가 발생했습니다.")
        st.write("🔍 상세 오류 메시지:", e)
        return []

    # ── 여기부터는 정상 response 처리 로직 ──
    pairs = []
    for line in text.splitlines():
        if market=="타오바오" and "–" in line:
            ko, zh = [s.strip() for s in line.split("–",1)]
            pairs.append((ko, zh))
        elif market=="라쿠텐" and "," in line:
            ko, ja = [x.strip(" ()") for x in line.split(",",1)]
            pairs.append((ko, ja))
    return pairs[:n]

def crawl_links_http(keyword, num_links, market):
    headers = {"User-Agent":"Mozilla/5.0"}
    if market=="타오바오":
        url = f"https://world.taobao.com/search/search.htm?q={urllib.parse.quote(keyword)}"
    else:
        url = "https://brandavenue.rakuten.co.jp/all-sites/item/" + \
              f"?free_word={urllib.parse.quote(keyword)}&sale=0&inventory_flg=1"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    if market=="타오바오":
        for a in soup.select("a[href]"):
            href=a["href"]
            if "item.taobao.com" in href or "detail.tmall.com" in href:
                links.append(href)
            if len(links)>=num_links: break
    else:
        for a in soup.select("a[href*='brandavenue.rakuten.co.jp/item']"):
            links.append(a["href"])
            if len(links)>=num_links: break
    return list(dict.fromkeys(links))[:num_links]

def save_links_to_excel(links, batch_idx, category, market, template):
    today = datetime.now().strftime("%Y%m%d")
    safe_category = category.replace(" ", "_")
    filename = f"{market}_{safe_category}_{today}_batch{batch_idx}.xlsx"
    wb = openpyxl.load_workbook(template)
    sheet = wb.active
    for i, link in enumerate(links):
        sheet[f'B{i + 4}'] = link
    wb.save(filename)
    return filename

def main():
    st.title("마켓 소싱 자동화 프로그램 (웹버전)")

    # 1) 사용자 입력
    market = st.selectbox("마켓 선택", ["타오바오", "라쿠텐"])
    category = st.text_input("카테고리 입력 (예: 여름 여성 의류)")
    target   = st.text_input("타깃(대상) 입력 (예: 20~40대 여성)")
    num_keywords = st.number_input(
        "카테고리당 생성할 키워드 개수", min_value=1, max_value=20, value=3
    )
    num_links = st.number_input(
        "한 키워드당 크롤링할 링크 개수", min_value=1, max_value=20, value=10
    )

    # 2) 실행 버튼
    if st.button("실행"):
        # 입력 검증
        if not category or not target:
            st.error("❗️ 카테고리와 타깃을 모두 입력하세요.");
            return

        # 3) 키워드 생성
        kws = generate_keywords(category, target, num_keywords, market)
        if not kws:
            st.error("❗️ 키워드 생성에 실패했습니다.");
            return

        st.success(f"추천 키워드 쌍: {kws}")

        # 크롤링 직전에 추가
        st.write("🔖 테스트: 첫 키워드에서 가져온 링크 수:", len(crawl_links_http(kws[0][1], num_links, market)))

        # 4) 크롤링 및 파일 저장 준비
        template = taobao_template if market == "타오바오" else rakuten_template
        all_links = []
        batch_idx = 1
        filenames = []

        # 크롤링 직전에 추가
        st.write("🔖 테스트: 첫 키워드에서 가져온 링크 수:", len(crawl_links_http(kws[0][1], num_links, market)))


        # 5) 키워드별 크롤링
        for ko, keyword in kws:
            st.write(f"🔍 {keyword} 크롤링 중…")
            links = crawl_links_http(keyword, num_links, market)
            all_links.extend(links)

            # 50개 단위로 엑셀 저장
            while len(all_links) >= 50:
                fname = save_links_to_excel(
                    all_links[:50], batch_idx, category, market, template
                )
                filenames.append(fname)
                all_links = all_links[50:]
                batch_idx += 1

        # 크롤링 직전에 추가
        st.write("🔖 테스트: 첫 키워드에서 가져온 링크 수:", len(crawl_links_http(kws[0][1], num_links, market)))

        # 6) 남은 링크도 저장
        if all_links:
            fname = save_links_to_excel(
                all_links, batch_idx, category, market, template
            )
            filenames.append(fname)
    
        st.write("🔖 파일 목록(filenames):", filenames)
    
        if filenames:
            st.success("✅ 모든 작업 완료! 아래 버튼을 클릭해 파일을 다운로드하세요.")
            for fname in filenames:
                if os.path.exists(fname):
            # 파일을 바이너리로 읽어서 data 변수에 담기
                with open(fname, "rb") as f:
                    data = f.read()
                # 그 데이터를 다운로드 버튼에 넘겨줌
                st.download_button(
                    label=f"📥 {fname} 다운로드",
                    data=data,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.info("🗂️ 다운로드가 완료되었습니다.")

#       # 7) 완료 메시지
#        st.success("모든 작업 완료! 아래에서 결과 파일을 확인하세요:")
#        for fname in filenames:
#            if os.path.exists(fname):
#                st.write(f"📁 {fname}")

if __name__ == "__main__":
    main()

