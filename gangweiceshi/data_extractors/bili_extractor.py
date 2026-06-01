"""
B 站音频提取器 — yt-dlp + FFmpeg → mp3
支持 Cookie 防风控、自定义输出目录
"""

import logging
import os
import re

import yt_dlp

logger = logging.getLogger(__name__)

# 临时音频输出目录
DEFAULT_OUTPUT_DIR = "/tmp/bili_audio"


def extract_bv_id(url: str) -> str:
    """从 B 站链接中提取 BV 号

    Args:
        url: 视频链接（支持 bilibili.com/video/BV... 和 b23.tv 短链）

    Returns:
        BV 号字符串（如 BV1xx411c7mD），无法提取时返回 'unknown'
    """
    # 匹配标准 BV 号格式
    match = re.search(r"(BV[a-zA-Z0-9]{10})", url)
    if match:
        return match.group(1)
    # 匹配 av 号格式（旧版）
    match = re.search(r"av(\d+)", url, re.IGNORECASE)
    if match:
        return f"av{match.group(1)}"
    return "unknown"


def download_bili_audio(
    url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookiefile: str | None = None,
) -> str:
    """下载 B 站视频的最佳音频流，用 FFmpeg 提取为 mp3

    Args:
        url:         B 站视频链接
        output_dir:  输出目录（默认 /tmp/bili_audio）
        cookiefile:  Netscape 格式 Cookie 文件路径，
                     用于绕过 B 站 403 风控限制。
                     示例: '/cookies/bilibili.txt'

    Returns:
        生成的 .mp3 文件绝对路径

    Raises:
        RuntimeError: 下载或转换失败时抛出
    """
    os.makedirs(output_dir, exist_ok=True)
    bv_id = extract_bv_id(url)

    # 输出模板：/tmp/bili_audio/BV1xx411c7mD.%(ext)s
    outtmpl = os.path.join(output_dir, f"{bv_id}.%(ext)s")
    expected_mp3 = os.path.join(output_dir, f"{bv_id}.mp3")

    # 如果已存在同名 mp3，直接返回（避免重复下载）
    if os.path.isfile(expected_mp3):
        logger.info(f"音频已缓存: {expected_mp3}")
        return os.path.abspath(expected_mp3)

    ydl_opts: dict = {
        # ── 格式选择：仅下载最佳音频流 ──
        "format": "bestaudio/best",
        # ── FFmpeg 后处理：提取音频 → mp3 ──
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        # ── 输出路径 ──
        "outtmpl": outtmpl,
        # ── 日志控制 ──
        "quiet": True,
        "no_warnings": True,
        # ── 网络优化 ──
        "socket_timeout": 30,
        "retries": 3,
        # ── 合并为 mp3 后删除原始文件 ──
        "keepvideo": False,
    }

    # ── 防风控：Cookie 文件 ──
    # 当遇到 HTTP 403 (Forbidden) 时，说明 B 站触发了反爬风控。
    # 解决方法：
    #   1. 在浏览器登录 B 站后，用 EditThisCookie 等插件导出 Netscape 格式 Cookie
    #   2. 将 cookie 文件放入 ./cookies/bilibili.txt
    #   3. 在 docker-compose.yml 中挂载: - ./cookies:/cookies
    #   4. 取消下面这行的注释并传入 cookiefile 参数:
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
        logger.info(f"使用 Cookie 文件: {cookiefile}")

    logger.info(f"开始下载 B 站音频: {url} → {bv_id}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        # 清理可能的半成品文件
        if os.path.isfile(expected_mp3):
            os.remove(expected_mp3)
        raise RuntimeError(f"B 站音频下载失败: {e}") from e

    if not os.path.isfile(expected_mp3):
        raise RuntimeError(
            f"mp3 文件未生成，请检查链接是否有效或是否需要 Cookie: {url}"
        )

    abs_path = os.path.abspath(expected_mp3)
    size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    logger.info(f"音频下载完成: {abs_path} ({size_mb:.1f} MB)")

    return abs_path


