"""
Scrapling 使用指南 — 三种 Fetcher，一套 API
"""
from scrapling import Fetcher, StealthyFetcher, DynamicFetcher

# ============================================================
# 一、Fetcher — 普通 HTTP 请求（最快，适合不防爬的网站）
# ============================================================
print("=== 一、基础 Fetcher ===")

# get(url) 发 GET 请求，返回 Response 对象
page = Fetcher.get("https://httpbin.org/html")
print(page.status)       # 200 → HTTP 状态码

# 取页面标题
title = page.css("title")[0].text
print(title)             # 页面的 <title> 内容

# 取页面所有文字
print(page.text[:200])   # 前 200 个字符


# ============================================================
# 二、CSS 选择器 — 精确定位元素
# ============================================================
print("\n=== 二、CSS 选择器 ===")

hn = Fetcher.get("https://news.ycombinator.com")

# .css("选择器") → 返回匹配的所有元素列表
headlines = hn.css(".titleline > a")

for h in headlines[:3]:
    print(f"  · {h.text}")      # ← .text 取标签内文字

# 取链接地址
first_link = headlines[0]
print(f"\n  链接地址: {first_link.attr('href')}")  # ← .attr() 取任意属性


# ============================================================
# 三、提取数据的关键方法
# ============================================================
print("\n=== 三、核心方法速查 ===")

# .css("选择器")    → 按 CSS 选择器找，返回 list
# .xpath("//div")   → 按 XPath 找，返回 list
# .text             → 当前节点包含的全部文字
# .attr("属性名")    → 取 href/src/class 等属性值
# .status           → HTTP 状态码
# .json             → 如果返回 JSON，直接转 dict


# ============================================================
# 四、StealthyFetcher — 隐身模式（防检测）
# ============================================================
# 用法和 Fetcher 一模一样，但请求看起来更像真人浏览器
# 适合 Cloudflare 保护、有反爬机制的网站
#
# from scrapling import StealthyFetcher
# page = StealthyFetcher.get("https://有反爬的网站.com")


# ============================================================
# 五、DynamicFetcher — 浏览器模式
# ============================================================
# 启动真实浏览器（Playwright），适合需要 JS 渲染的 SPA 网站
# from scrapling import DynamicFetcher
# page = DynamicFetcher.fetch("https://react网站.com")
