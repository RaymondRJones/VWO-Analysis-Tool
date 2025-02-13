import pytest
import sqlite3
import difflib
import time
import urllib.parse
from langchain_openai import ChatOpenAI
from vwo_tracker_with_web_crawling import (
    fetch_page,
    extract_vwo_data,
    get_last_snapshot,
    find_html_differences,
    analyze_with_chatopenai,
    save_variation_to_db,
    crawl_site,
)

class DummyResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

def dummy_requests_get_success(url, headers, timeout):
    return DummyResponse(200, "Dummy page content")

def dummy_requests_get_fail(url, headers, timeout):
    return DummyResponse(404, "")

def test_fetch_page_success(monkeypatch):
    monkeypatch.setattr("vwo_tracker_with_web_crawling.requests.get", dummy_requests_get_success)
    content = fetch_page("http://example.com")
    assert content == "Dummy page content"

def test_fetch_page_failure(monkeypatch):
    monkeypatch.setattr("vwo_tracker_with_web_crawling.requests.get", dummy_requests_get_fail)
    content = fetch_page("http://example.com")
    assert content is None

def test_extract_vwo_data():
    html = '<html><body><div data-vwo="123">Test</div><p>No data</p></body></html>'
    result = extract_vwo_data(html)
    assert len(result) == 1
    assert "data-vwo" in result[0]

def test_find_html_differences():
    old_html = "<html><body><div>Old</div></body></html>"
    new_html = "<html><body><div>New</div></body></html>"
    diff = find_html_differences(old_html, new_html)
    assert "Old" in diff
    assert "New" in diff

def test_analyze_with_chatopenai(monkeypatch):
    monkeypatch.setattr(ChatOpenAI, "invoke", lambda self, messages: type("DummyResponse", (), {"content": "Dummy analysis"})())
    analysis = analyze_with_chatopenai("dummy diff text")
    assert analysis == "Dummy analysis"

PAGES = {
    "http://test.com": '<html><body><a href="/page1">Page1</a></body></html>',
    "http://test.com/page1": '<html><body>No links here</body></html>',
}

def dummy_fetch_page(url):
    return PAGES.get(url, None)

def test_crawl_site(monkeypatch):
    monkeypatch.setattr("vwo_tracker_with_web_crawling.fetch_page", dummy_fetch_page)
    result = crawl_site("http://test.com", max_depth=1)
    assert "http://test.com" in result
    assert "http://test.com/page1" in result

def test_save_and_get_last_snapshot(monkeypatch):
    test_conn = sqlite3.connect(":memory:")
    test_cursor = test_conn.cursor()
    test_cursor.execute('''
    CREATE TABLE IF NOT EXISTS base_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_page_url TEXT UNIQUE
    )
    ''')
    test_cursor.execute('''
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
    test_conn.commit()
    import vwo_tracker_with_web_crawling
    vwo_tracker_with_web_crawling.conn = test_conn
    vwo_tracker_with_web_crawling.cursor = test_cursor

    base_page_url = "http://example.com"
    html = "<html><body>Test</body></html>"
    vwo_elements = ["<div data-vwo='test'>A/B Test</div>"]
    ai_analysis = "Analysis"
    html_diff = "diff"
    ai_analysis_diff = "analysis diff"

    save_variation_to_db(base_page_url, html, vwo_elements, ai_analysis, html_diff, ai_analysis_diff)
    snapshot = get_last_snapshot(base_page_url)
    assert snapshot == html

