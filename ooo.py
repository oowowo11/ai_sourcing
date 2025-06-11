import os
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["LC_ALL"] = "en_US.UTF-8"
os.environ["LANG"] = "en_US.UTF-8"
import streamlit as st
import openai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import openpyxl
import urllib.parse
import time
from datetime import datetime
import os

# 1. 본인 OpenAI 키로 수정
client = openai.OpenAI(api_key="여기에_본인_API_KEY_입력")

# 2. 엑셀 템플릿 파일명 (필요에 따라 경로 수정)
taobao_template = "123.xlsx"
rakuten_template = "퍼센티_다양한_카테고리_엑셀_수집(쿠팡_기준).xlsx"

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

def generate_keywords(category, target, num_keywords, market):
    if market == "타오바오":
        prompt = (
            f"{target}를 대상으로 하는 {category} 카테고리에서 "
            f"최근 트렌디하고 인기 있는 프리미엄 상품 {num_keywords}가지를 추천해 주세요. "
            f"상품명은 한국어와 중국어로 각각 제공해 주시고, "
            f"중국어는 타오바오에서 자연스러운 용어로 작성해 주세요.\n"
            f"유명 브랜드나 상표명, 이미 추천된 상품은 포함하지 마세요.\n"
            f"아래 형식으로 답변해 주세요:\n"
            f"<한국어 상품명> – <중국어 상품명>\n"
        )
        system_msg = "당신은 중국 크로스보더 이커머스 트렌드 상품 전문가입니다."
    else:
        prompt = (
            f"일본 라쿠텐 Brand Avenue에서 인기 있는 상품 키워드 {num_keywords}쌍을 추천해 주세요.\n"
            f"- (한국어, 일본어) 쌍으로 한 줄에 하나씩, 총 {num_keywords}줄로 써 주세요.\n"
            f"카테고리는 {category}, 타깃은 {target}입니다.\n"
            f"예시: (서머 드레스, サマードレス)"
        )
        system_msg = "당신은 일본 패션, 라이프스타일 이커머스 트렌드에 능통한 전문가입니다."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        text = response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI 키 또는 네트워크 오류: {e}")
        return []
    pairs = []
    for line in text.splitlines():
        if market == "타오바오" and "–" in line:
            ko, zh = [s.strip() for s in line.split("–", 1)]
            pairs.append((ko, zh))
        elif market == "라쿠텐" and "," in line:
            ko, ja = [x.strip(" ()") for x in line.split(",")]
            pairs.append((ko, ja))
    return pairs[:num_keywords]

def crawl_links(driver, keyword, num_links, market):
    if market == "타오바오":
        encoded = urllib.parse.quote(keyword)
        url = f"https://world.taobao.com/search/search.htm?q={encoded}"
        driver.get(url)
        time.sleep(5)
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        elements = driver.find_elements(By.XPATH, '//a[@href]')
        links = []
        for el in elements:
            href = el.get_attribute("href")
            if href and ("item.taobao.com" in href or "detail.tmall.com" in href):
                links.append(href)
            if len(links) >= num_links:
                break
        return list(dict.fromkeys(links))[:num_links]
    else:
        encoded = urllib.parse.quote(keyword)
        base_url = f"https://brandavenue.rakuten.co.jp/all-sites/item/?free_word={encoded}&sale=0&inventory_flg=1"
        links = []
        for page in range(1, 6):
            page_url = base_url if page == 1 else f"{base_url}&p={page}"
            driver.get(page_url)
            time.sleep(5)
            items = driver.find_elements(By.XPATH, '//li[starts-with(@id,"search-rpp-item-")]//a[contains(@href,"brandavenue.rakuten.co.jp/item")]')
            if not items:
                items = driver.find_elements(By.XPATH, '//a[contains(@href,"brandavenue.rakuten.co.jp/item")]')
            for el in items:
                href = el.get_attribute("href")
                if href and href not in links:
                    links.append(href)
                if len(links) >= num_links:
                    return links[:num_links]
            if len(links) >= num_links:
                break
        return links[:num_links]

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
        if not (category and target):
            st.error("카테고리, 타깃을 모두 입력하세요!")
            return
        template = taobao_template if market == "타오바오" else rakuten_template
        st.info("키워드 추천 → 크롤링 → 엑셀 저장 작업을 진행합니다. (수분 소요)")
        st.write("작업 진행상황은 터미널에서도 확인 가능, 결과 파일은 폴더에 저장됩니다.")

        keyword_pairs = generate_keywords(category, target, num_keywords, market)
        if not keyword_pairs:
            st.error("키워드 생성에 실패했습니다. OpenAI 키를 다시 확인하거나 입력값을 수정해보세요.")
            return

        st.success(f"추천 키워드 쌍: {keyword_pairs}")
        st.warning("크롬 창이 자동으로 뜨며, 타오바오일 경우 로그인 필요(QR 로그인 추천)")

        driver = setup_driver("zh-CN" if market == "타오바오" else "ja-JP")
        if market == "타오바오":
            driver.get("https://world.taobao.com")
            st.info("타오바오 로그인을 완료한 뒤 터미널에서 [Enter]를 눌러주세요.")
            input("타오바오 로그인 후 터미널에서 [Enter]를 누르세요...")

        all_links = []
        batch_idx = 1
        filenames = []
        for pair in keyword_pairs:
            keyword = pair[1]
            st.write(f"🔍 검색중: {keyword}")
            links = crawl_links(driver, keyword, num_links, market)
            all_links.extend(links)
            while len(all_links) >= 50:
                fname = save_links_to_excel(all_links[:50], batch_idx, category, market, template)
                filenames.append(fname)
                all_links = all_links[50:]
                batch_idx += 1
        if all_links:
            fname = save_links_to_excel(all_links, batch_idx, category, market, template)
            filenames.append(fname)
        driver.quit()
        st.success("모든 작업 완료! 아래에서 결과 파일을 확인하세요:")
        for fname in filenames:
            if os.path.exists(fname):
                st.write(f"📁 {fname}")

if __name__ == "__main__":
    main()
