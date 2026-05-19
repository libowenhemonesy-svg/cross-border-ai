# LLM 核心概念 — AI 应用工程师必备

## 1. Prompt Engineering（提示词工程）

### 基本结构
```
┌─────────────────────────────┐
│  System Prompt（系统提示）    │  ← 定义角色、规则、输出格式
├─────────────────────────────┤
│  Context（上下文）           │  ← 知识库检索结果、用户信息
├─────────────────────────────┤
│  Few-shot Examples（示例）   │  ← 输入输出范例
├─────────────────────────────┤
│  User Message（用户消息）    │  ← 实际提问
└─────────────────────────────┘
```

### 核心技术对比

| 技术 | 说明 | 示例 |
|------|------|------|
| **Zero-shot** | 不给示例，直接提问 | "翻译下面文本为英文：..." |
| **Few-shot** | 给 2-5 个示例，再提问 | "Q: 苹果→A: apple\nQ: 香蕉→A: " |
| **Chain-of-Thought (CoT)** | 要求逐步推理 | "让我们一步步思考..." |
| **ReAct** | 推理 + 行动交替 | "Thought: ... Action: ... Observation: ..." |
| **Self-Consistency** | 多次采样，投票选最优 | 同一 prompt 调用 5 次，多数决定 |

### 实战 Prompt 模板

#### RAG 问答模板
```python
RAG_PROMPT = """你是一个专业的知识问答助手。请严格依据以下参考资料回答问题。

参考资料：
{context}

规则：
1. 只使用参考资料中的信息回答
2. 如果资料中没有相关信息，明确说"参考资料中未找到相关信息"
3. 回答时引用资料编号，如 [1]、[2]
4. 用中文回答

用户问题：{question}
回答："""
```

#### Function Calling 提示
```python
TOOL_PROMPT = """你可以使用以下工具：

1. search_knowledge_base(query: str) — 搜索内部知识库
2. get_weather(city: str) — 查询天气
3. calculate(expression: str) — 数学计算

当需要使用工具时，返回 JSON：
{"tool": "工具名", "args": {"参数": "值"}}

用户：今天北京天气怎么样？
助手：{"tool": "get_weather", "args": {"city": "北京"}}"""
```

### System Prompt 最佳实践
```python
SYSTEM_PROMPT = """# 角色
你是一个技术客服助手，擅长解答编程和 DevOps 问题。

# 行为准则
- 回答简洁，不超过 300 字
- 代码示例使用 ```python 包裹
- 不确定时主动建议用户查阅官方文档
- 禁止编造 API 或配置参数

# 输出格式
1. 先给出直接答案
2. 再提供代码示例（如适用）
3. 最后列出参考链接（如有）"""
```

---

## 2. RAG（检索增强生成）

### 完整 RAG 流程

```
                   ┌─────────────┐
  知识文档 →        │  文档分块     │
  (PDF/MD/TXT)     │  Chunking    │
                   └──────┬──────┘
                          ↓
                   ┌─────────────┐
                   │  Embedding   │
                   │  向量化       │
                   └──────┬──────┘
                          ↓
                   ┌─────────────┐
                   │  向量数据库   │
                   │  PGVector    │
                   └──────┬──────┘
                          ↑
 用户提问 → Embedding ──→ 相似度检索
                          ↓
                   ┌─────────────┐
    检索结果 +      │  Prompt 构建  │
    原始问题 →       │              │
                   └──────┬──────┘
                          ↓
                   ┌─────────────┐
                   │  LLM 生成    │
                   │  最终回答     │
                   └─────────────┘
```

### 文档分块策略

| 策略 | 说明 | 适用 |
|------|------|------|
| **固定大小** | 按字符数切分，500-1000 字符 | 通用场景 |
| **句子分割** | 按句子边界切分 | 问答场景 |
| **语义分割** | 用模型判断语义边界 | 高质量要求 |
| **递归分割** | 先按段落→句子→词逐级切 | LangChain 默认 |

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,        # 每块最大字符数
    chunk_overlap=50,      # 块之间重叠 50 字符，防止关键信息被切断
    separators=["\n\n", "\n", "。", ".", " ", ""]  # 优先在段落边界切
)

chunks = splitter.split_text(long_document)
```

### RAG 进阶策略

| 策略 | 说明 | 解决的问题 |
|------|------|----------|
| **Small-to-Big** | 检索时用小 chunk，生成时用大 chunk | 检索精度 vs 生成完整度 |
| **HyDE** | 用户问题→生成假设答案→用假设答案做检索 | 问题短、和文档语言不一致 |
| **Multi-Query** | 一个问题生成多个变体分别检索 | 提高召回率 |
| **Re-ranking** | 初检索 Top-20 → 精排模型 → Top-3 | 提高精度 |
| **Self-RAG** | LLM 自己判断检索结果是否相关 | 减少无关内容 |

```python
# Re-ranking 示例
async def search_with_rerank(query: str) -> list[str]:
    # 1. 快速向量检索（高召回）
    candidates = await vector_store.search(query, top_k=20)

    # 2. 用 Cross-Encoder 精排（高精度）
    from sentence_transformers import CrossEncoder
    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    pairs = [[query, doc["content"]] for doc in candidates]
    scores = model.predict(pairs)

    # 3. 按分数排序取 Top-3
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [doc["content"] for doc, _ in ranked[:3]]
```

### RAG 评估指标
- **召回率 (Recall)**：相关文档被检出的比例
- **精确率 (Precision)**：检出文档中相关的比例
- **MRR**（Mean Reciprocal Rank）：第一个相关文档的排名倒数
- **答案忠实度**：生成答案是否忠实于检索到的文档
- **答案相关性**：生成答案是否回答用户问题

---

## 3. Embedding（向量嵌入）

### 常用模型

| 模型 | 维度 | 特点 |
|------|------|------|
| OpenAI text-embedding-3-small | 512/1536 | 性价比高 |
| OpenAI text-embedding-3-large | 256/1024/3072 | 质量最高 |
| BGE-M3 (BAAI) | 1024 | 多语言、开源 |
| Cohere Embed v3 | 1024 | 支持多种输入类型 |
| Jina Embeddings v2 | 768 | 支持 8192 token 长文本 |

```python
from openai import OpenAI

client = OpenAI()
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="这是一个测试文本",
    dimensions=512  # 可以降维节省存储
)
vector = response.data[0].embedding  # [0.01, -0.02, ...] 长度 512
```

### Embedding 成本估算
```
OpenAI text-embedding-3-small: $0.02 / 1M tokens
100 万篇文档 × 1000 tokens/篇 = 10 亿 tokens = $20 一次性成本
```

---

## 4. Function Calling / Tool Use

### OpenAI 格式
```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 北京"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    tools=tools,
    tool_choice="auto"  # auto / none / required / 指定工具
)

# 解析工具调用
if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    # tool_call.function.name → "get_weather"
    # tool_call.function.arguments → '{"city": "北京"}'

    # 执行工具
    weather = get_weather(city="北京")

    # 将结果返回给 LLM
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(weather)
    })
    # 再次调用 LLM 生成最终回答
    final = client.chat.completions.create(model="gpt-4", messages=messages)
```

### Anthropic 格式
```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=[
        {
            "name": "get_weather",
            "description": "查询指定城市的天气",
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    ],
    messages=[{"role": "user", "content": "北京天气？"}]
)

# response.stop_reason == "tool_use" 表示需要调用工具
```

---

## 5. Token 计算与成本控制

### Token 概念
- **1 token ≈ 0.75 个英文单词 ≈ 0.5 个汉字**
- GPT-4 Turbo 上下文：128K tokens ≈ 300 页书
- Claude 上下文：200K tokens ≈ 500 页书

### 成本公式
```
总成本 = (输入 tokens × 输入单价) + (输出 tokens × 输出单价)

# GPT-4 Turbo: 输入 $10/M, 输出 $30/M
# 一次问答 1000 输入 + 500 输出 =
# (1000/1M × $10) + (500/1M × $30) = $0.01 + $0.015 = $0.025
```

### Token 计数 (tiktoken)
```python
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4")
tokens = enc.encode("你好世界")
print(len(tokens))  # 每个中文约 1.5-2 tokens

# 估算成本
def estimate_cost(messages: list[dict], model: str = "gpt-4") -> dict:
    enc = tiktoken.encoding_for_model(model)
    input_tokens = sum(len(enc.encode(m["content"])) for m in messages)
    estimated_output = 500  # 估算输出
    return {
        "input_tokens": input_tokens,
        "est_cost": (input_tokens / 1e6 * 10) + (estimated_output / 1e6 * 30)
    }
```

---

## 6. 流式输出 (Streaming / SSE)

### 为什么需要流式
- **用户体验**：等 10 秒看空白页面 → 逐字输出有反馈感
- **超时问题**：长文本生成可能超过网关超时限制
- **并发优化**：边生成边返回，不占用连接

```python
# OpenAI 流式
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "写一篇 500 字的文章"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### FastAPI SSE 完整实现
```python
from fastapi.responses import StreamingResponse
import json

async def stream_llm_response(prompt: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            },
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=120.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        yield f"data: {json.dumps({'token': content, 'done': False})}\n\n"

            yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

@app.post("/chat/stream")
async def chat_stream(prompt: str):
    return StreamingResponse(
        stream_llm_response(prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",     # 禁用 Nginx 缓冲
            "Content-Encoding": "none"      # 禁用压缩缓冲
        }
    )
```

---

## 总结检查清单

- [ ] 能写 System Prompt / User Prompt / Few-shot 示例
- [ ] 理解 Chain-of-Thought 和 ReAct 的区别
- [ ] 能画出完整 RAG 架构图
- [ ] 知道文档分块策略和重叠参数的选择依据
- [ ] 理解 Embedding 模型维度对存储和精度的影响
- [ ] 能实现 OpenAI Function Calling 的完整闭环
- [ ] 能计算 Token 用量和成本
- [ ] 能实现 SSE 流式输出
- [ ] 知道至少 3 种 RAG 进阶策略（HyDE / Re-rank / Multi-Query）
