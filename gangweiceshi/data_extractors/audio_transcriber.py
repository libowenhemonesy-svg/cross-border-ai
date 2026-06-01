"""
ASR 音频转录服务 — OpenAI 兼容 Whisper API
将 mp3 音频文件转写为带基础标点的长文本
"""

import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

# 默认 ASR 配置
DEFAULT_ASR_MODEL = "TeleAI/TeleSpeechASR"


def transcribe_audio(
    file_path: str,
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = DEFAULT_ASR_MODEL,
) -> str:
    """调用 OpenAI 兼容的 Whisper API 将音频转写为文本

    Args:
        file_path: mp3 音频文件路径
        api_key:   API 密钥
        base_url:  API 基础地址（默认 OpenAI 官方，可替换为兼容服务）
                   示例:
                     - OpenAI 官方:   https://api.openai.com/v1
                     - 硅基流动:      https://api.siliconflow.cn/v1
                     - 阿里云百炼:    https://dashscope.aliyuncs.com/compatible-mode/v1
        model:     模型名称（默认 whisper-1）

    Returns:
        转写后的完整文本（含基础标点、分段）

    Raises:
        FileNotFoundError: 音频文件不存在
        RuntimeError:      API 调用或转写失败
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    logger.info(f"开始转录: {file_path} ({file_size_mb:.1f} MB)")

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        with open(file_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
            )

        # Transcription 对象取 .text 属性
        text = response.text

        word_count = len(text)
        logger.info(
            f"转录完成: {word_count} 字符 "
            f"(模型={model}, 文件={os.path.basename(file_path)})"
        )
        return text

    except Exception as e:
        raise RuntimeError(f"音频转录失败 [{model}]: {e}") from e
