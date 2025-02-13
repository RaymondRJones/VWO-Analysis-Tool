import requests
import time
import hashlib
import sqlite3
import difflib
import urllib.parse
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
# Add your own API Key Here
OPENAI_API_KEY = os.getenv("OPENAPI_KEY")

BASE_URL = "https://www.bragg.com/"
conn = sqlite3.connect("vwo_ab_tests.db")
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS base_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base_page_url TEXT UNIQUE
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS page_variations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base_page_id INTEGER,
    timestamp TEXT,
    page_hash TEXT,
    vwo_elements TEXT,
    full_html TEXT,
    ai_analysis TEXT,
    html_diff TEXT,
    ai_analysis_diff TEXT,
    FOREIGN KEY (base_page_id) REFERENCES base_pages(id)
)
''')
conn.commit()

def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            print(f"[-] HTTP {response.status_code} error fetching {url}")
    except Exception as e:
        print(f"[-] Exception fetching {url}: {e}")
    return None

def extract_vwo_data(html):
    soup = BeautifulSoup(html, "html.parser")
    return [str(tag) for tag in soup.find_all(attrs={"data-vwo": True})]

def get_last_snapshot(url):
    cursor.execute("SELECT full_html FROM page_variations pv JOIN base_pages bp ON pv.base_page_id = bp.id WHERE bp.base_page_url = ? ORDER BY pv.id DESC LIMIT 1", (url,))
    row = cursor.fetchone()
    return row[0] if row else None

def find_html_differences(old_html, new_html):
    if not old_html:
        return "No previous snapshot available."
    old_lines = old_html.splitlines()
    new_lines = new_html.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
    return "\n".join(diff) if diff else "No major changes detected."

def analyze_with_chatopenai(diff_text):
    if not diff_text.strip() or diff_text.startswith("No previous snapshot"):
        return "No significant changes detected."
    messages = [
        {"role": "system", "content": "You are an expert in A/B testing and website analytics."},
        {"role": "user", "content": f"Below are the HTML differences detected between two snapshots:\n\n{diff_text}\n\nPlease describe what elements changed and describe them from a UI A/B Testing perspective. Based on the html differences, I'd like to know what A/B testing strategies were done (i.e variations in banners, buttons, or CTAs). If there are no significant differences, just say 'No major changes detected'"}
    ]
    llm = ChatOpenAI(api_key=OPENAI_API_KEY, model_name="gpt-4o-mini")
    try:
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        print("Error with ChatOpenAI:", e)
        return "LLM analysis failed."

def save_variation_to_db(base_page_url, html, vwo_elements, ai_analysis, html_diff, ai_analysis_diff):
    page_hash = hashlib.sha256(html.encode()).hexdigest()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR IGNORE INTO base_pages (base_page_url) VALUES (?)", (base_page_url,))
    conn.commit()
    cursor.execute("SELECT id FROM base_pages WHERE base_page_url = ?", (base_page_url,))
    row = cursor.fetchone()
    base_page_id = row[0] if row else None
    if base_page_id is None:
        print("Error: Unable to get base_page_id for", base_page_url)
        return
    cursor.execute("INSERT INTO page_variations (base_page_id, timestamp, page_hash, vwo_elements, full_html, ai_analysis, html_diff, ai_analysis_diff) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (base_page_id, timestamp, page_hash, "\n".join(vwo_elements), html, ai_analysis, html_diff, ai_analysis_diff))
    conn.commit()
    print(f"[+] Saved variation for {base_page_url} at {timestamp}")

def monitor_ab_tests(urls, interval=300):
    last_snapshots = {url: get_last_snapshot(url) for url in urls}
    while True:
        for url in urls:
            print(f"\n[*] Processing URL: {url}")
            html = fetch_page(url)
            if not html:
                print(f"[-] Skipping {url} due to fetch error.")
                continue
            vwo_elements = extract_vwo_data(html)
            diff_text = find_html_differences(last_snapshots.get(url), html)
            print(f"[~] Diff for {url}:\n{diff_text[:300]}{'...' if len(diff_text) > 300 else ''}")
            ai_analysis = analyze_with_chatopenai(diff_text)
            print(f"[~] AI Analysis for {url}:\n{ai_analysis}")
            save_variation_to_db(url, html, vwo_elements, ai_analysis, diff_text, ai_analysis)
            last_snapshots[url] = html
        print(f"[*] Waiting {interval} seconds before next check...")
        time.sleep(interval)

def main():
    pages_to_monitor = [
        "https://www.bragg.com/products/organic-apple-cider-vinaigrette"
    ]
    print(f"[*] Monitoring the following pages:")
    for page in pages_to_monitor:
        print(f" - {page}")
    monitor_ab_tests(pages_to_monitor, interval=60)

if __name__ == '__main__':
    main()

