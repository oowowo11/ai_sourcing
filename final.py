import openai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import openpyxl
import urllib.parse
import time
from datetime import datetime

client = openai.OpenAI(api_key="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")

def setup_driver(lang="zh-CN"):
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
        """
        if lang == "zh-CN" else
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """
    })
    return driver

def generate_keywords_taobao(product_category, target_audience, num_keywords):
    prompt = (
        f"{target_audience}를 대상으로 하는 {product_category} 카테고리에서 "
        f"최근 트렌디하고 인기 있는 프리미엄 상품 {num_keywords}가지를 추천해 주세요. "
        f"상품명은 한국어와 중국어로 각각 제공해 주시고, "
        f"중국어는 타오바오에서 자연스러운 용어로 작성해 주세요.\n"
        f"유명 브랜드나 상표명, 이미 추천된 상품은 포함하지 마세요.\n"
        f"아래 형식으로 답변해 주세요:\n"
        f"<한국어 상품명> – <중국어 상품명>\n"
        f"예시:\n여름 샌들 – 夏季凉鞋\n쿨링 스카프 – 凉感围巾\n선풍기 – 电风扇\n"
    )
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 중국 크로스보더 이커머스 트렌드 상품 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0.7,
    )
    text = response.choices[0].message.content.strip()
    parsed = []
    for line in text.splitlines():
        if "–" in line:
            ko, zh = [s.strip() for s in line.split("–", 1)]
            parsed.append((ko, zh))
    return parsed[:num_keywords]

def generate_keywords_rakuten(product_category, target_audience, num_keywords):
    prompt = (
        f"일본 라쿠텐 Brand Avenue에서 인기 있는 상품 키워드 {num_keywords}쌍을 추천해 주세요.\n"
        f"- (한국어, 일본어) 쌍으로 한 줄에 하나씩, 총 {num_keywords}줄로 써 주세요.\n"
        f"카테고리는 {product_category}, 타깃은 {target_audience}입니다.\n"
        f"예시: (서머 드레스, サマードレス)"
    )
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 일본 패션, 라이프스타일 이커머스 트렌드에 능통한 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0.7,
    )
    text = response.choices[0].message.content.strip()
    pairs = []
    for line in text.splitlines():
        if "," in line:
            ko, ja = [x.strip(" ()") for x in line.split(",")]
            pairs.append((ko, ja))
    return pairs[:num_keywords]

def crawl_links_taobao(driver, zh_keyword, num_links):
    encoded = urllib.parse.quote(zh_keyword)
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

def crawl_links_rakuten(driver, ja_keyword, num_links):
    encoded = urllib.parse.quote(ja_keyword)
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

def save_links_to_excel_generic(links, batch_idx, category, market, template):
    today = datetime.now().strftime("%Y%m%d")
    safe_category = category.replace(" ", "_")
    filename = f"{market}_{safe_category}_{today}_batch{batch_idx}.xlsx"
    wb = openpyxl.load_workbook(template)
    sheet = wb.active
    for i, link in enumerate(links):
        sheet[f'B{i + 4}'] = link
    wb.save(filename)
    print(f"✅ [{market} Batch {batch_idx}] {filename} 저장 완료 ({len(links)}개)")

def run_taobao(category, target, num_keywords, num_links):
    print("\n📦 GPT로부터 키워드 쌍 추출 중...")
    keyword_pairs = generate_keywords_taobao(category, target, num_keywords)
    print("\n🔑 추출된 키워드 쌍:")
    for ko, zh in keyword_pairs:
        print(f"  {ko} – {zh}")
    driver = setup_driver(lang="zh-CN")
    driver.get("https://world.taobao.com")
    input("🔓 타오바오 로그인 후 [Enter] 눌러주세요... (QR 추천)")
    all_links = []
    batch_idx = 1
    for kr_keyword, zh_keyword in keyword_pairs:
        print(f"\n🔍 검색어(중국어): {zh_keyword} | 저장이름(한글): {kr_keyword}")
        links = crawl_links_taobao(driver, zh_keyword, num_links)
        all_links.extend(links)
        while len(all_links) >= 50:
            save_links_to_excel_generic(all_links[:50], batch_idx, category, "타오바오", "123.xlsx")
            all_links = all_links[50:]
            batch_idx += 1
    if all_links:
        save_links_to_excel_generic(all_links, batch_idx, category, "타오바오", "123.xlsx")
    driver.quit()
    print("\n모든 작업 완료!")

def run_rakuten(category, target, num_keywords, num_links):
    print("\n📦 GPT로부터 키워드 쌍 추출 중...")
    keyword_pairs = generate_keywords_rakuten(category, target, num_keywords)
    print("\n🔑 추출된 키워드 쌍:")
    for ko, ja in keyword_pairs:
        print(f"  {ko} – {ja}")
    driver = setup_driver(lang="ja-JP")
    all_links = []
    batch_idx = 1
    for kr_keyword, ja_keyword in keyword_pairs:
        print(f"\n🔍 검색어(일본어): {ja_keyword} | 저장이름(한글): {kr_keyword}")
        links = crawl_links_rakuten(driver, ja_keyword, num_links)
        all_links.extend(links)
        while len(all_links) >= 50:
            save_links_to_excel_generic(all_links[:50], batch_idx, category, "라쿠텐", "퍼센티 다양한 카테고리 엑셀 수집(쿠팡 기준).xlsx")
            all_links = all_links[50:]
            batch_idx += 1
    if all_links:
        save_links_to_excel_generic(all_links, batch_idx, category, "라쿠텐", "퍼센티 다양한 카테고리 엑셀 수집(쿠팡 기준).xlsx")
    driver.quit()
    print("\n모든 작업 완료!")

if __name__ == "__main__":
    print("=== 마켓 소싱 자동화 프로그램 ===\n")
    market = input("1) 마켓 선택 (타오바오/라쿠텐) : ").strip()
    category = input("2) 카테고리 입력 (예: 여름 여성 의류): ").strip()
    target = input("3) 타깃(대상) 입력 (예: 20~40대 여성): ").strip()
    num_keywords = int(input("4) 카테고리당 생성할 키워드 개수 (예: 3): ").strip())
    num_links = int(input("5) 한 키워드당 크롤링할 링크 개수 (예: 10): ").strip())

    if "타오바오" in market:
        run_taobao(category, target, num_keywords, num_links)
    elif "라쿠텐" in market:
        run_rakuten(category, target, num_keywords, num_links)
    else:
        print("지원하지 않는 마켓입니다. '타오바오' 또는 '라쿠텐'만 입력하세요.")
