# Python 核心 — AI 应用工程师必备

## 1. 异步编程 (async/await)

### 为什么重要
AI 应用的核心特征是 **IO 密集型**——调用 LLM API 需要等 2-30 秒，同时可能有几十个并发请求。同步阻塞会让系统吞吐量极低。

### 基础语法
```python
import asyncio
import httpx

# 错误示范 — 同步阻塞
def call_llm_sync(prompt: str) -> str:
    response = requests.post("https://api.openai.com/v1/chat/completions", ...)  # 阻塞 5 秒
    return response.json()

# 正确示范 — 异步
async def call_llm(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": prompt}]},
            timeout=60.0
        )
    return response.json()

# 并发调用多个 LLM
async def batch_llm_calls(prompts: list[str]) -> list[str]:
    async with httpx.AsyncClient() as client:
        tasks = [call_llm(p) for p in prompts]
        results = await asyncio.gather(*tasks)  # 并发执行
    return results
```

### 关键知识点
| 概念 | 说明 |
|------|------|
| `async def` | 定义协程函数，调用返回协程对象 |
| `await` | 暂停当前协程直到可等待对象完成 |
| `asyncio.gather()` | 并发运行多个协程，等全部完成 |
| `asyncio.create_task()` | 创建后台任务，立即返回 |
| `asyncio.wait_for()` | 设置超时 |
| `asyncio.Semaphore` | 限制并发数，防止触发 API 限流 |

### 常见陷阱
```python
# 陷阱1: 在协程内使用阻塞库 (requests, time.sleep)
async def bad():
    import requests
    requests.get(...)        # ❌ 阻塞整个事件循环
    time.sleep(5)            # ❌ 阻塞整个事件循环

async def good():
    import httpx
    async with httpx.AsyncClient() as c:
        await c.get(...)      # ✅ 真正的异步
    await asyncio.sleep(5)    # ✅ 不阻塞事件循环

# 陷阱2: 忘记 await
async def bad2():
    asyncio.sleep(1)         # ❌ 返回协程对象但不执行，直接跳过

async def good2():
    await asyncio.sleep(1)   # ✅ 正确等待

# 陷阱3: 循环中创建任务不限制并发
async def bad3(urls):
    tasks = [fetch(url) for url in urls]  # 10000 个并发可能打爆 API
    return await asyncio.gather(*tasks)

async def good3(urls):
    sem = asyncio.Semaphore(10)           # 最多 10 个并发
    async def bounded_fetch(url):
        async with sem:
            return await fetch(url)
    tasks = [bounded_fetch(url) for url in urls]
    return await asyncio.gather(*tasks)
```

---

## 2. 类型提示 (Type Hints)

### 为什么重要
现代 AI 框架（LangChain、LlamaIndex、OpenAI SDK）全部使用类型提示。面试中展示类型提示能力是加分项。

```python
from typing import Optional, Union, Literal, TypedDict, NotRequired
from collections.abc import AsyncIterator, Callable, Awaitable

# 基础类型
def chat(
    messages: list[dict[str, str]],
    model: str = "gpt-4",
    temperature: float = 0.7,
) -> str: ...

# Optional — 可能为 None
def get_user(user_id: int) -> Optional[dict]: ...

# Union — 多种类型之一
def process_input(data: Union[str, list[str], dict]) -> str: ...

# Literal — 限定具体值
def set_model(model: Literal["gpt-4", "gpt-3.5", "claude-3"]) -> None: ...

# TypedDict — 结构化字典
class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str
    name: NotRequired[str]  # 可选字段

class CompletionResponse(TypedDict):
    content: str
    tokens_used: int
    finish_reason: Literal["stop", "length", "tool_calls"]

# 复杂回调类型
Handler = Callable[[ChatMessage], Awaitable[CompletionResponse]]

# 泛型
from typing import TypeVar
T = TypeVar("T")

class LRUCache(dict[str, T]):
    def get_or_set(self, key: str, factory: Callable[[], T]) -> T: ...
```

### 运行时检查 — Pydantic（AI 领域标配）
```python
from pydantic import BaseModel, Field, field_validator

class LLMConfig(BaseModel):
    model: str = "gpt-4"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    top_p: float = Field(default=1.0, ge=0, le=1)

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str) -> str:
        allowed = {"gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "claude-3-opus"}
        if v not in allowed:
            raise ValueError(f"不支持的模型: {v}")
        return v
```

---

## 3. 装饰器

```python
import functools
import time
from collections.abc import Callable

# 重试装饰器 — AI 调用必备
def retry(max_attempts: int = 3, backoff_factor: float = 2):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        wait = backoff_factor ** attempt
                        print(f"重试 {attempt + 1}/{max_attempts}，等待 {wait}s")
                        await asyncio.sleep(wait)
            raise last_error
        return wrapper
    return decorator

# 使用
@retry(max_attempts=3, backoff_factor=2)
async def call_llm_with_retry(prompt: str) -> str:
    # API 调用可能临时失败，自动重试
    ...
```

---

## 4. FastAPI — AI 服务框架

### 最小可运行服务
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI(title="AI 问答服务")

class QuestionRequest(BaseModel):
    question: str
    context: str | None = None

class AnswerResponse(BaseModel):
    answer: str
    sources: list[str]
    tokens_used: int

@app.post("/ask", response_model=AnswerResponse)
async def ask_question(req: QuestionRequest) -> AnswerResponse:
    """RAG 问答接口"""
    try:
        # 1. 向量检索相关文档
        docs = await vector_search(req.question)

        # 2. 构建 prompt
        prompt = build_rag_prompt(req.question, docs)

        # 3. 调用 LLM
        answer = await call_llm(prompt)

        return AnswerResponse(
            answer=answer["content"],
            sources=[d["title"] for d in docs],
            tokens_used=answer["tokens"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 流式输出 (SSE)
```python
from fastapi.responses import StreamingResponse
import json

@app.post("/ask/stream")
async def ask_stream(req: QuestionRequest):
    async def event_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": req.question}],
                    "stream": True
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}
            ) as response:
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: "):
                        data = chunk[6:]
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        yield f"data: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"       # 禁用 nginx 缓冲
        }
    )
```

### 中间件 — 限流、日志、认证
```python
from fastapi import Request
import time

@app.middleware("http")
async def log_and_limit(request: Request, call_next):
    # 请求日志
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"{request.method} {request.url.path} — {duration:.2f}s — {response.status_code}")
    return response
```

---

## 5. 上下文管理器

```python
from contextlib import asynccontextmanager

# 数据库连接管理
@asynccontextmanager
async def get_db():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()

async def fetch_user(user_id: int):
    async with get_db() as db:
        return await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

# LLM 客户端生命周期
class LLMClient:
    def __init__(self, api_key: str):
        self._client = httpx.AsyncClient(headers={"Authorization": f"Bearer {api_key}"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def chat(self, prompt: str) -> str: ...

async def main():
    async with LLMClient(api_key="...") as llm:
        answer = await llm.chat("你好")
```

---

## 6. 生成器

```python
# 大文件分块 — 文档处理常用
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """将长文本分割为重叠块"""
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        chunks.append(chunk)
    return chunks

# 生成器版本 — 节省内存
def chunk_text_gen(text: str, chunk_size: int = 500, overlap: int = 50):
    for i in range(0, len(text), chunk_size - overlap):
        yield text[i : i + chunk_size]

# 异步生成器 — 流式处理
async def stream_tokens(client: httpx.AsyncClient, prompt: str):
    """逐 token 产出，适合 SSE"""
    async with client.stream("POST", LLM_URL, json={...}) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                token = json.loads(line[6:])["choices"][0]["delta"]["content"]
                yield token
```

---

## 总结：AI 应用工程师 Python 技术栈检查清单

- [ ] `async/await`：能写出并发 LLM 调用，理解事件循环
- [ ] `asyncio.Semaphore`：控制 API 并发，防止限流
- [ ] `httpx.AsyncClient`：异步 HTTP 客户端
- [ ] `FastAPI` + `Pydantic`：构建 AI API 服务
- [ ] `StreamingResponse` / SSE：流式输出 LLM 结果
- [ ] 类型提示 + `TypedDict`：提高代码可维护性
- [ ] 装饰器模式：重试、日志、缓存
- [ ] 上下文管理器：资源生命周期管理
- [ ] `asyncio.gather` vs `create_task`：理解区别
- [ ] 生成器：分块处理大数据
