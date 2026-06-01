"""
联调脚本 — 向 /api/process_bilibili 发送 B 站视频链接
触发完整的「下载 → 转录 → AI 提取 → 入库」闭环
"""

import httpx

API_URL = "http://localhost:8000/api/process_bilibili"

# B 站 AI 趋势演讲视频（替换为你实际要处理的视频链接）
# 示例: 李开复《AI 2.0 时代的创业机会》或类似科技演讲
PAYLOAD = {
    "url": "https://www.bilibili.com/video/BV1GJcmzyEev/",
}

print(f"向 {API_URL} 发送 B 站视频处理请求...")
print(f"目标链接: {PAYLOAD['url']}")
print()
print("全链路流程: 下载音频 → ASR 转录 → AI 语义处理 → Obsidian 入库 → 清理临时文件")
print("预计耗时: 30-120 秒（取决于视频时长和 API 响应速度）")
print()

with httpx.Client(timeout=300.0) as client:
    try:
        resp = client.post(API_URL, json=PAYLOAD)
        print(f"HTTP {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"状态:       {data.get('status')}")
            print(f"输出文件:   {data.get('filepath')}")
            print(f"AI 摘要:    {data.get('summary')}")
            print(f"核心观点:   {data.get('key_points')}")
            print(f"标签:       {data.get('tags')}")
            preview = data.get("transcript_preview", "")
            if preview:
                print(f"转录预览:   {preview}...")
            print()
            print("请在 Obsidian 中打开生成的 .md 文件查看完整笔记。")
        elif resp.status_code == 422:
            print("转录失败 — 音频可能无有效语音内容，或 ASR 端点不可用")
            print("响应:", resp.text[:500])
        elif resp.status_code == 500:
            print("服务器内部错误:")
            print("响应:", resp.text[:500])
        else:
            print("响应:", resp.text[:500])

    except httpx.ConnectError:
        print("连接失败 — 请确认 python_api 容器是否正在运行 (docker compose up -d)")
    except httpx.ReadTimeout:
        print("请求超时 — 视频可能较长，转录耗时超过了 300 秒限制")
    except Exception as e:
        print(f"请求异常: {e}")
