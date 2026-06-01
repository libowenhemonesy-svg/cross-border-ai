# Bilibili to Obsidian Demo

一个用于岗位测试的最小可运行 Demo：输入 Bilibili 视频链接，读取 `cookie.txt`，抓取视频元信息和字幕，将结果整理成 Obsidian 可直接打开的 Markdown 知识库笔记。

## 功能

- 解析 Bilibili 链接中的 BV 号
- 使用 `cookie.txt` 访问视频页面和字幕接口
- 提取标题、UP 主、简介、发布时间、分 P 信息
- 优先读取 Bilibili 自带字幕作为“转文字”结果
- 自动生成摘要、关键词和 Obsidian 标签
- 输出 Markdown 文件到 Obsidian Vault 目录

## 运行方式

```powershell
python .\bilibili_obsidian_demo\bilibili_to_obsidian.py `
  --url "https://www.bilibili.com/video/BVxxxxxxx" `
  --cookie "C:\path\to\cookie.txt" `
  --vault "C:\path\to\ObsidianVault"
```

如果没有现成 Vault，可以先输出到当前目录：

```powershell
python .\bilibili_obsidian_demo\bilibili_to_obsidian.py `
  --url "https://www.bilibili.com/video/BVxxxxxxx" `
  --cookie "C:\path\to\cookie.txt" `
  --vault ".\obsidian_vault"
```

## 关于 scrapling

脚本会优先尝试使用本机安装的 `scrapling` 作为页面获取工具；如果当前 Python 环境没有安装，则自动回退到标准库请求方式。这样便于在不同电脑上演示，不会因为环境差异直接中断。

## Demo 边界

- Bilibili 平台字幕不是每个视频都有；如果没有字幕，脚本会生成“待转写”段落。
- 生产版可以在没有字幕时下载音频，并接入 Whisper / faster-whisper / 讯飞等模型完成语音转文字。
- Cookie 仅通过命令行参数读取，不写入仓库文件，避免泄露账号凭据。
