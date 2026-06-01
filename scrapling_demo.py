"""Scrapling 实战演示 — 抓取网页并解析"""
from scrapling import Fetcher

print("=" * 50)
print("Scrapling 演示")
print("=" * 50)

# 1. 基础请求
print("\n[1] Fetcher 抓取页面...")
page = Fetcher.get("https://httpbin.org/html")
print(f"    状态码: {page.status}")
# 用 CSS 取标题
title_el = page.css("title")
if title_el:
    print(f"    标题: {title_el[0].text}")

# 2. 取页面正文
body_tag = page.css("body")
if body_tag:
    print(f"    前100字符: {body_tag[0].text[:100]}...")

# 3. Hacker News 抓取
print("\n[2] 抓取 Hacker News 头条...")
try:
    hn = Fetcher.get("https://news.ycombinator.com", timeout=15)
    headlines = hn.css(".titleline > a")
    for i, h in enumerate(headlines[:5]):
        print(f"    {i+1}. {h.text}")
except Exception as e:
    print(f"    跳过: {e}")

# 4. 获取所有链接
print("\n[3] 抓取页面所有链接...")
links = page.css("a")
for i, link in enumerate(links[:5]):
    print(f"    {i+1}. {link.text.strip()} -> {link.attr('href')}")

print("\n" + "=" * 50)
print("Scrapling 演示完成！HTTP 抓取能力正常")
