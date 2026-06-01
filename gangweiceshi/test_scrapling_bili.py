"""
Scrapling 抓取 B 站视频页面测试 — 验证能否成功获取视频信息、评论等数据
"""
import scrapling
import json


def test_bili_video_page():
    """测试抓取 B 站视频页面元数据"""
    url = "https://www.bilibili.com/video/BV1ize4zgEir/"

    print(f"正在抓取: {url}\n")

    # Scrapling 自带 curl_cffi 引擎，可以模拟浏览器 TLS 指纹绕过反爬
    f = scrapling.Fetcher()

    try:
        page = f.get(url)  # Response 对象本身就是 Selector，可以直接用 css/xpath

        # ── 1. 页面标题 ──
        title = page.css("title::text").get()
        print(f"[标题] {title}")

        # ── 2. HTTP 状态码 ──
        print(f"[状态码] {page.status}")

        # ── 3. 视频标题 (meta 标签) ──
        meta_title = page.css('meta[property="og:title"]::attr(content)').get()
        print(f"[OG标题] {meta_title}")

        # ── 4. 视频描述 ──
        meta_desc = page.css('meta[property="og:description"]::attr(content)').get()
        print(f"[描述] {meta_desc}")

        # ── 5. 视频标签/关键词 ──
        meta_keywords = page.css('meta[name="keywords"]::attr(content)').get()
        print(f"[关键词] {meta_keywords}")

        # ── 6. 脚本数据提取 (B 站将初始数据嵌入 script 标签)
        scripts = page.css("script::text").getall()
        found_state = False
        for script in scripts:
            if "window.__INITIAL_STATE__" in script:
                found_state = True
                # 打印匹配行上下文
                idx = script.find("window.__INITIAL_STATE__")
                start_ctx = max(0, idx - 50)
                end_ctx = min(len(script), idx + 100)
                print(f"  [上下文] ...{script[start_ctx:end_ctx]}...")

                # 尝试找到 JSON 起始位置
                import re
                match = re.search(
                    r'window\.__INITIAL_STATE__\s*=\s*', script
                )
                if match:
                    json_start = match.end()
                    # 用括号计数器定位 JSON 对象的结束位置
                    depth = 0
                    json_end = json_start
                    in_string = False
                    escape = False
                    for i in range(json_start, len(script)):
                        ch = script[i]
                        if escape:
                            escape = False
                            continue
                        if ch == '\\':
                            escape = True
                            continue
                        if ch == '"' and not in_string:
                            in_string = True
                            continue
                        if ch == '"' and in_string:
                            in_string = False
                            continue
                        if not in_string:
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    json_end = i + 1
                                    break
                        # 安全检查：JSON 一般不会超过 20MB
                        if i - json_start > 20_000_000:
                            break

                    json_str = script[json_start:json_end]
                    print(f"  [JSON 长度] {len(json_str)} 字符 (从 {json_start} 到 {json_end})")

                    try:
                        data = json.loads(json_str)
                        print(f"  [顶层 keys] {list(data.keys())[:20]}")
                        if "videoData" in data:
                            vd = data["videoData"]
                            print(f"\n=== 视频数据 ===")
                            print(f"[BV号] {vd.get('bvid', 'N/A')}")
                            stat = vd.get('stat', {})
                            print(f"[播放量] {stat.get('view', 'N/A')}")
                            print(f"[弹幕数] {stat.get('dm', 'N/A')}")
                            print(f"[评论数] {stat.get('reply', 'N/A')}")
                            print(f"[收藏数] {stat.get('favorite', 'N/A')}")
                            print(f"[硬币数] {stat.get('coin', 'N/A')}")
                            print(f"[分享数] {stat.get('share', 'N/A')}")
                            print(f"[点赞数] {stat.get('like', 'N/A')}")
                            print(f"[发布时间] {vd.get('pubdate', 'N/A')}")
                            print(f"[视频简介] {str(vd.get('desc', ''))[:300]}")
                            print(f"[分区] {vd.get('tname', 'N/A')}")
                            owner = vd.get('owner', {})
                            print(f"[UP主UID] {owner.get('mid', 'N/A')}")
                            print(f"[UP主名称] {owner.get('name', 'N/A')}")
                            print(f"[视频封面] {vd.get('pic', 'N/A')}")
                            tags_data = vd.get('tag', [])
                            if tags_data:
                                print(f"[标签] {[t.get('tag_name','') for t in tags_data]}")
                        # 检查是否有其他有用字段
                        # UP主详细数据
                        up_data = data.get('upData', {})
                        if up_data:
                            print(f"\n=== UP主数据 ===")
                            print(f"[粉丝数] {up_data.get('fans', 'N/A')}")
                            print(f"[视频数] {up_data.get('archive_count', 'N/A')}")
                            print(f"[签名] {str(up_data.get('sign', ''))[:200]}")
                            print(f"[认证] {up_data.get('official_verify', {}).get('desc', 'N/A')}")
                        # 标签
                        tags = data.get('tags', [])
                        if tags:
                            print(f"[tags] {tags}")
                        # 相关视频
                        related = data.get('related', [])
                        if related:
                            print(f"\n[相关视频 Top 5]")
                            for r in related[:5]:
                                print(f"  - {r.get('title','')} | 播放:{r.get('stat',{}).get('view','?')} | UP:{r.get('owner',{}).get('name','?')}")
                    except json.JSONDecodeError as e:
                        print(f"  JSON 解析失败: {e}")
                else:
                    print("  正则未匹配")
                break

        if not found_state:
            print("  [警告] 未找到 window.__INITIAL_STATE__")

        # ── 6. 尝试获取 UP 主卡片信息 ──
        up_name_el = page.css(".up-name__text::text").get()
        print(f"\n[UP主名称(dom)] {up_name_el or '未找到'}")

        # ── 7. 标签 tag 列表 ──
        tag_els = page.css(".tag-link__text::text").getall()
        print(f"[视频标签] {tag_els}")

        # ── 8. 可见简介文本 ──
        desc_el = page.css(".basic-desc-info .basic-desc::text").get()
        print(f"[可见简介] {str(desc_el)[:300] if desc_el else '未找到'}")

        # ── 9. 播放量显示 ──
        view_el = page.css(".video-info-detail .view-text::text").get()
        print(f"[播放量文本] {view_el or '未找到'}")

        print("\n=== 抓取成功 ===")

    except Exception as e:
        print(f"抓取失败: {e}")


if __name__ == "__main__":
    test_bili_video_page()
