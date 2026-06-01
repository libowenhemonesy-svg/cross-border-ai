"""
AI 处理器 — 兼容国内 OpenAI 标准接口（硅基流动 / 阿里云百炼）
支持中英文双语内容提取，英文内容自动启用逐句精读模式（含对齐翻译与词汇标注）
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, InternalServerError

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """AI 从长文本中提取的结构化内容"""
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    modules: list[dict] = field(default_factory=list)    # 模块化知识卡片 (v4.0)
    tags: list[str] = field(default_factory=list)
    source_url: str = ""
    full_text: str = ""                                  # 原始全文（转录/输入文本）
    close_reading: list[dict] = field(default_factory=list)  # 逐句精读数据


class AIProcessor:
    """国内模型接口通用调用类

    支持所有兼容 OpenAI /v1/chat/completions 的国内厂商：
      - 硅基流动: https://api.siliconflow.cn/v1
      - 阿里云百炼: https://dashscope.aliyuncs.com/compatible-mode/v1
    """

    BASE_URL = "https://api.siliconflow.cn/v1"

    # ---- 中文内容模块化知识提取 Prompt (v4.0) ----
    EXTRACT_PROMPT_CN = """你是一个专业的跨境电商知识管理员。你的任务是将长文本（通常来自视频语音转录）转化为结构化的知识卡片，分模块记录，便于日后检索和复盘。

严格按 JSON 格式返回，不要输出任何其他内容。

═══════════════════════════════════════════
## 输出结构
═══════════════════════════════════════════

{
  "summary": "认知收获（一句话讲清"看完这篇我学到了什么"）",
  "modules": [
    {
      "title": "模块标题",
      "items": ["要点1", "要点2", "要点3"]
    }
  ],
  "key_points": ["向后兼容，等于所有模块 items 的合集"],
  "tags": ["标签1", "标签2", "标签3"]
}

═══════════════════════════════════════════
## 模块类型（从以下 6 类中选择 2-4 个合适的，宁缺毋滥）
═══════════════════════════════════════════

1. **可操作方法** — 具体的步骤、流程、技巧、SOP。每条写清楚"在什么情况下、做什么、怎么做"。教程类内容的默认首选模块。
2. **数据参考** — 文中提到的具体数字、价格、薪资、比例、时间周期等量化信息。便于日后横向对比。
3. **避坑指南** — 常见错误、失败教训、风险提醒、不该做的事。每条包含"错误做法 → 后果 → 正确做法"。
4. **行业洞察** — 对行业趋势、竞争格局、平台规则变化的判断和观察。需要有原文依据而非凭空发挥。
5. **工具资源** — 提到的软件、网站、插件、书籍、服务商等具体资源。
6. **案例拆解** — 文中作为案例讲的具体产品或店铺，包含背景、做法、结果。

═══════════════════════════════════════════
## 要求
═══════════════════════════════════════════

- **summary**：必须是认知收获（"学到了什么"），不是内容摘要（"讲了什么"）。控制在 60 字以内，一针见血。
- **每个模块 2-5 条要点**，每条 15-80 字，包含具体细节。拒绝"要重视选品"这种废话，要写"选品前用 JS 插件看竞品月销量，低于 300 单的细分类目慎入"这种能落地的。
- **模块按内容选择**，不相关的不要硬凑。一个纯教程视频可能只有"可操作方法"，一个行业分析可能只有"数据参考+行业洞察"。
- **tags**：3-5 个精准标签，优先用电商专业术语。
- 如果文本是闲聊、无实质内容，modules 可以是空数组，summary 如实写"无实质知识内容"。

═══════════════════════════════════════════
## 文本内容
═══════════════════════════════════════════

"""

    # ---- 英文内容精读 Prompt（逐句对齐翻译 + 商业/技术词汇标注） ----
    EXTRACT_PROMPT_EN = """You are an expert bilingual content analyst specializing in cross-border e-commerce and AI technology. Analyze the following English text and return a structured JSON response. Do NOT output anything other than valid JSON.

────────────────────────────────────────────
## ANALYSIS REQUIREMENTS
────────────────────────────────────────────

### 1. summary
A one-sentence Chinese summary (≤50 Chinese characters) capturing the core thesis.

### 2. key_points
Exactly 3 key insights in Chinese. Each ≤30 characters. Focus on actionable business implications.

### 3. tags
3-5 relevant tags in Chinese (e.g., "RAG架构", "跨境电商AI", "向量检索").

### 4. close_reading (CRITICAL — this is the most important section)
Select 4-6 complex, information-dense English sentences from the source text. These sentences should:
- Carry substantive business or technical meaning (not filler / transitions).
- Contain specialized terminology worth annotating.
- Be representative of the text's key arguments.

For EACH selected sentence, provide a structured object with:

| Field        | Requirement |
|--------------|-------------|
| `original`   | The exact English sentence, unmodified. |
| `translation`| A precise, exam-quality Chinese translation. Translate technical terms accurately; preserve business nuance; make the Chinese read naturally while staying faithful to the source. The standard must match **CATTI Level 2 (China Accreditation Test for Translators and Interpreters)** — professional, fluent, and terminologically precise. |
| `vocabulary` | An array of 2-5 key business/technical terms found in this specific sentence. Each term as: `{"term": "english term", "annotation": "≤30-character Chinese explanation in cross-border e-commerce context"}` |

────────────────────────────────────────────
## OUTPUT SCHEMA (strict JSON)
────────────────────────────────────────────

{
  "summary": "中文一句话摘要",
  "key_points": ["中文核心观点1", "中文核心观点2", "中文核心观点3"],
  "tags": ["标签1", "标签2", "标签3"],
  "close_reading": [
    {
      "original": "The exact original English sentence.",
      "translation": "精准的中文翻译，对标CATTI二级翻译质量标准。",
      "vocabulary": [
        {"term": "RAG", "annotation": "检索增强生成，结合信息检索与文本生成"},
        {"term": "vector database", "annotation": "向量数据库，存储高维嵌入向量的专用数据库"}
      ]
    }
  ]
}

────────────────────────────────────────────
## TEXT TO ANALYZE
────────────────────────────────────────────

"""

    def __init__(self, api_key: str, model: str = "deepseek-ai/DeepSeek-V3"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.BASE_URL)
        self.model = model

    # ------------------------------------------------------------------
    #  语言检测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_primarily_english(text: str, threshold: float = 0.65) -> bool:
        """启发式检测文本是否主要为英文（基于字母 vs CJK 字符比例）"""
        if not text:
            return False
        alpha_count = sum(1 for c in text if c.isascii() and c.isalpha())
        cjk_count = sum(1 for c in text if '一' <= c <= '鿿')
        total = alpha_count + cjk_count
        if total == 0:
            return False
        return alpha_count / total >= threshold

    def _build_prompt(self, text: str) -> str:
        """根据文本语言自动选择 Prompt 模板"""
        if self._is_primarily_english(text):
            logger.info("检测为英文文本，启用逐句精读模式")
            return self.EXTRACT_PROMPT_EN + text
        logger.info("检测为中文文本，使用标准提取模式")
        return self.EXTRACT_PROMPT_CN + text

    # ------------------------------------------------------------------
    #  指数退避重试机制
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self, messages: list[dict], max_retries: int = 3
    ) -> str:
        """带指数退避（Exponential Backoff）的 API 调用

        仅在遇到以下可恢复错误时重试：
          - HTTP 429 (Rate Limit / 并发限制)
          - HTTP 504 (Gateway Timeout)
          - 请求超时 (APITimeoutError)
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content

            except RateLimitError as e:
                last_error = e
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt  # 1s → 2s → 4s
                logger.warning(
                    f"触发限流 (429)，第 {attempt+1}/{max_retries} 次重试，"
                    f"{wait}s 后重试..."
                )
                await asyncio.sleep(wait)

            except (APITimeoutError, InternalServerError) as e:
                last_error = e
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(
                    f"服务端超时/错误 ({type(e).__name__})，"
                    f"第 {attempt+1}/{max_retries} 次重试，{wait}s 后重试..."
                )
                await asyncio.sleep(wait)

            except Exception:
                # 不可恢复错误（如 401 认证失败），立即抛出
                raise

        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    #  异步提取
    # ------------------------------------------------------------------

    async def extract_async(
        self, text: str, source_url: str = ""
    ) -> ExtractedContent:
        """异步核心处理函数

        从长文本中提取摘要、观点、标签；
        英文内容自动启用「逐句对齐精读」模块，返回结构化 close_reading 数据。
        """
        if not text or not text.strip():
            logger.warning("输入文本为空，返回空结果")
            return ExtractedContent()

        prompt = self._build_prompt(text)

        try:
            raw = await self._call_with_retry([
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的跨境电商与AI技术内容分析助手，"
                        "擅长从长文本中提炼关键信息。严格按 JSON 格式输出，"
                        "不要输出任何 JSON 之外的内容。"
                    ),
                },
                {"role": "user", "content": prompt},
            ])

            data = json.loads(raw)

            # 解析模块化知识卡片 (v4.0)
            modules = data.get("modules", [])
            # 向后兼容：如果 LLM 没返回 modules 但有 key_points，自动包装
            if not modules and data.get("key_points"):
                modules = [{"title": "核心观点", "items": data["key_points"]}]

            # 向后兼容：如果 LLM 返回了 modules 但没返回 key_points，自动生成
            key_points = data.get("key_points", [])
            if not key_points and modules:
                key_points = []
                for m in modules:
                    key_points.extend(m.get("items", []))

            result = ExtractedContent(
                summary=data.get("summary", ""),
                key_points=key_points[:10],
                modules=modules,
                tags=data.get("tags", [])[:5],
                source_url=source_url,
                full_text=text,
                close_reading=data.get("close_reading", []),
            )
            logger.info(
                f"AI 提取成功 — summary={result.summary[:40]}..., "
                f"modules={len(result.modules)}个模块, "
                f"tags={result.tags}, "
                f"close_reading={len(result.close_reading)}条"
            )
            return result

        except Exception as e:
            logger.error(f"AI 提取失败: {e}")
            return ExtractedContent(
                summary=f"[提取失败] {e}",
                source_url=source_url,
            )

    # ------------------------------------------------------------------
    #  同步包装器（向后兼容）
    # ------------------------------------------------------------------

    def extract(self, text: str, source_url: str = "") -> ExtractedContent:
        """同步包装器 — 保持对旧调用方的兼容"""
        return asyncio.run(self.extract_async(text, source_url))
