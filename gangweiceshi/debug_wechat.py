"""对比两个公众号文章的可访问性"""
import sys
sys.path.insert(0, "/app")
import httpx
import re

ua = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.128 Mobile Safari/537.36 MicroMessenger/8.0.42"

urls = {
    "秋芝2046": "https://mp.weixin.qq.com/s/xRlGxEsyMQFPGGs70WqNyg",
    "亚马逊Amazon": "https://mp.weixin.qq.com/s/wakfgGfFWMX5l767NSTniQ",
}

for name, url in urls.items():
    print(f"=== {name} ===")
    try:
        with httpx.Client(timeout=30, follow_redirects=True,
                          headers={"User-Agent": ua}) as c:
            r = c.get(url)
            print(f"HTTP {r.status_code}, {len(r.text)} 字节")

            html = r.text

            if "请在微信客户端打开" in html:
                print(">>> 被拦截：需要微信客户端打开 <<<")
            elif "环境异常" in html:
                print(">>> 被拦截：环境异常 <<<")
            elif "var biz" in html or "rich_media_content" in html:
                print("页面正常，含文章正文")

            # 标题
            m = re.search(
                r'<h1[^>]*id="activity-name"[^>]*>(.*?)</h1>',
                html, re.DOTALL,
            )
            if m:
                title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                print(f"标题: {title[:80]}")

            # biz
            m = re.search(r'var\s+biz\s*=\s*"([^"]+)"', html)
            if m:
                print(f"biz: {m.group(1)}")

            # 文章链接
            links = re.findall(
                r'https?://mp\.weixin\.qq\.com/s/([^"#\s&\x27<>]+)',
                html,
            )
            unique = list(set(links))
            print(f"页内文章链接: {len(unique)} 个")
            for l in unique:
                print(f"  /s/{l[:50]}...")

            # 正文长度
            m = re.search(
                r'<div[^>]*id="js_content"[^>]*>(.*?)</div>',
                html, re.DOTALL,
            )
            if m:
                content = re.sub(r"<[^>]+>", "", m.group(1))
                print(f"正文字数: {len(content)}")

    except Exception as e:
        print(f"失败: {e}")
    print()
