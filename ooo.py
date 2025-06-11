import os
import streamlit as st
import openai
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import openpyxl
import urllib.parse
import time
from datetime import datetime
import os

# 1) OpenAI 키
openai.api_key = os.environ.get("OPENAI_API_KEY")
if not openai.api_key:
    st.error("OPENAI_API_KEY 설정 필요!")
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

    market = st.selectbox("마켓 선택", ["타오바오", "라쿠텐"])
    category = st.text_input("카테고리 입력 (예: 여름 여성 의류)")
    target = st.text_input("타깃(대상) 입력 (예: 20~40대 여성)")
    num_keywords = st.number_input("카테고리당 생성할 키워드 개수", min_value=1, max_value=20, value=3)
    num_links = st.number_input("한 키워드당 크롤링할 링크 개수", min_value=1, max_value=20, value=10)

    run = st.button("실행")

    if run:
    
        # 입력 검사 …
        kws = generate_keywords(category, target, num_keywords, market)
        # …
        all_links=[]; batch=1; files=[]
        for ko, keyword in kws:
            st.write(f"🔍 {keyword} 크롤링 중…")
            links = crawl_links_http(keyword, num_links, market)
        st.success("모든 작업 완료! 아래에서 결과 파일을 확인하세요:")
        for fname in filenames:
            if os.path.exists(fname):
                st.write(f"📁 {fname}")

if __name__ == "__main__":
    main()
