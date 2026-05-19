# Agent 与框架 — AI 应用工程师必备

## 1. Agent 架构

### 什么是 Agent
Agent 是具有自主决策能力的 AI 系统。与普通 LLM 调用的区别：

| | 普通 LLM 调用 | Agent |
|------|-----------|-------|
| 决策 | 一次性输入→输出 | 多步推理→行动→观察→再推理 |
| 工具 | 无 | 调用 API、数据库、代码执行 |
| 记忆 | 仅当前对话 | 长期记忆 + 短期记忆 |
| 规划 | 无 | 任务分解、子目标制定 |

### Agent 核心架构（ReAct 模式）
```
┌─────────────────────────────────────┐
│              Agent 主循环             │
│                                      │
│  Thought（思考）：分析当前状态        │
│      ↓                               │
│  Action（行动）：选择并调用工具        │
│      ↓                               │
│  Observation（观察）：获取工具返回值   │
│      ↓                               │
│  是否完成？——否→ 回到 Thought         │
│      ↓ 是                            │
│  Final Answer（最终回答）             │
└─────────────────────────────────────┘
```

### 代码实现
```python
from enum import Enum
from pydantic import BaseModel
import json

class AgentState(Enum):
    THINKING = "thinking"
    ACTING = "acting"
    FINISHED = "finished"

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: str

class SimpleAgent:
    def __init__(self, llm, tools: dict):
        self.llm = llm                    # LLM 客户端
        self.tools = tools                # {"tool_name": function}
        self.memory: list[dict] = []      # 对话记忆

    async def run(self, task: str) -> str:
        self.memory = [{"role": "system", "content": self._system_prompt()}]
        self.memory.append({"role": "user", "content": task})

        max_steps = 10
        for step in range(max_steps):
            response = await self.llm.chat(self.memory)
            self.memory.append({"role": "assistant", "content": response})

            # 解析 Agent 的响应，判断是工具调用还是最终回答
            if "FINAL:" in response:
                return response.split("FINAL:")[1].strip()

            tool_call = self._parse_tool(response)
            if tool_call:
                result = await self._execute_tool(tool_call)
                self.memory.append({
                    "role": "user",
                    "content": f"工具 {tool_call['name']} 返回: {result}"
                })

        return "Agent 达到最大步数限制"

    def _system_prompt(self) -> str:
        tool_desc = "\n".join([
            f"- {name}: {fn.__doc__}" for name, fn in self.tools.items()
        ])
        return f"""你是自主 Agent，可以调用工具完成任务。

可用工具：
{tool_desc}

规则：
1. 思考后再行动
2. 调用工具时返回：TOOL: {{"name": "工具名", "args": {{...}}}}
3. 任务完成时返回：FINAL: 最终答案
"""
```

---

## 2. 多 Agent 协作

### 常见模式

| 模式 | 说明 | 适用 |
|------|------|------|
| **顺序流水线** | A→B→C→D 链式处理 | 内容审核→翻译→润色 |
| **管理者-执行者** | 一个 Agent 分配任务给多个专业 Agent | 复杂任务分解 |
| **辩论模式** | 多个 Agent 从不同角度讨论，达成一致 | 需要多视角决策 |
| **层级模式** | 树形结构，上级分配、下级执行、汇总 | 大型项目 |

### 最小多 Agent 示例
```python
async def debate_agents(topic: str) -> str:
    """两个 Agent 辩论，第三个裁判做决定"""

    pro_agent = SimpleAgent(llm, tools={"search": web_search})
    con_agent = SimpleAgent(llm, tools={"search": web_search})
    judge_agent = SimpleAgent(llm, tools={})

    # 第一轮：正反方发言
    pro_argument = await pro_agent.run(f"论证「{topic}」的正面理由")
    con_argument = await con_agent.run(f"论证「{topic}」的反面理由")

    # 第二轮：互相反驳
    pro_rebuttal = await pro_agent.run(f"反驳这个观点：{con_argument}")
    con_rebuttal = await con_agent.run(f"反驳这个观点：{pro_argument}")

    # 裁判总结
    verdict = await judge_agent.run(f"""
    基于以下辩论内容，给出平衡的结论：
    正方：{pro_rebuttal}
    反方：{con_rebuttal}
    """)

    return verdict
```

---

## 3. MCP 协议（Model Context Protocol）

### 概述
Anthropic 提出的标准化协议，让 LLM 通过统一接口访问外部工具和数据源。

```
┌──────────┐    MCP 协议    ┌──────────────┐
│ LLM 客户端 │ ←───────────→ │ MCP Server    │
│ (Claude)  │  JSON-RPC     │ (工具/数据)    │
└──────────┘               └──────────────┘
                                ├── 文件系统
                                ├── 数据库
                                ├── API 服务
                                └── ...
```

### MCP 核心概念
- **Tools**：可调用的函数（类似 Function Calling）
- **Resources**：可读取的数据源（文件、数据库表等）
- **Prompts**：预定义的提示模板

```python
# MCP Server 伪代码
from mcp import Server, Tool

server = Server("my-ai-tools")

@server.tool()
async def search_docs(query: str, top_k: int = 5) -> list[dict]:
    """搜索内部文档"""
    return await vector_store.search(query, top_k)

@server.resource("file://docs/{path}")
async def read_doc(path: str) -> str:
    """读取文档内容"""
    return (Path("docs") / path).read_text()

server.run(transport="stdio")
```

---

## 4. LangChain / LlamaIndex

### 框架对比

| | LangChain | LlamaIndex |
|------|-----------|------------|
| **定位** | 通用 LLM 应用框架 | 专注数据索引和检索 |
| **核心抽象** | Chain、Agent、Tool | Index、QueryEngine、Node |
| **优势** | 生态大、集成多、Agent 强 | 数据连接器多、检索策略丰富 |
| **劣势** | 抽象层过多、调试难 | 生成能力依赖 LangChain |
| **适合** | 复杂 Agent、多工具编排 | 文档问答、知识库 |

### LangChain 核心概念

```python
# 1. Chain — 串联多个步骤
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser

prompt = ChatPromptTemplate.from_template("翻译成英文：{text}")
model = ChatOpenAI(model="gpt-4")
chain = prompt | model | StrOutputParser()  # LCEL 语法

result = chain.invoke({"text": "你好世界"})  # "Hello World"

# 2. Tool — 可被 Agent 调用的函数
from langchain.tools import tool

@tool
def search_knowledge(query: str) -> str:
    """搜索内部知识库"""
    return vector_store.similarity_search(query)

# 3. Agent Executor
from langchain.agents import AgentExecutor, create_openai_functions_agent

agent = create_openai_functions_agent(llm=model, tools=[search_knowledge])
executor = AgentExecutor(agent=agent, tools=[search_knowledge])
result = executor.invoke({"input": "公司年假政策是什么？"})
```

### LangChain 优缺点（面试常见问题）

**优点：**
- 快速原型开发
- 丰富的 Loader（PDF、CSV、数据库...）
- 内置多种 RAG 策略
- LangSmith 调试工具

**缺点：**
- 封装过度，黑盒调试困难
- 版本更新频繁，API 不稳定
- 生产环境性能开销大
- 不必要的抽象（有时候直接调 API 更简单）

### LlamaIndex 快速上手
```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

# 从目录加载文档并建索引
documents = SimpleDirectoryReader("./docs").load_data()
index = VectorStoreIndex.from_documents(documents)

# 查询
query_engine = index.as_query_engine()
response = query_engine.query("什么是 RAG？")
print(response)
```

---

## 5. 模型微调 (Fine-tuning)

### 概念对比

| 方法 | 说明 | 成本 | 适用 |
|------|------|------|------|
| **Full Fine-tuning** | 更新所有参数 | $$$$ | 大公司 |
| **LoRA** | 只训练低秩矩阵，冻结主模型 | $ | 行业定制 |
| **QLoRA** | LoRA + 4-bit 量化 | $ | 消费级 GPU |
| **Prompt Tuning** | 只训练 soft prompt | $$ | 特定任务 |
| **RLHF** | 人类反馈强化学习 | $$$$$ | 对齐微调 |

### LoRA 原理（一句话）
```
在原始权重矩阵旁边加一个低秩矩阵 A×B，只训练 A 和 B，
训练完成后合并回原矩阵，推理时无额外开销。
```

```python
# 使用 HuggingFace PEFT 做 LoRA
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3-8B")
lora_config = LoraConfig(
    r=8,                   # 秩（rank），越大表达能力越强
    lora_alpha=16,         # 缩放因子
    target_modules=["q_proj", "v_proj"],  # 应用 LoRA 的层
    lora_dropout=0.1
)
model = get_peft_model(model, lora_config)
# 可训练参数从 8B 降到 ~4M，减少 99.95%
```

---

## 6. 工具调用实践模式

### 错误处理
```python
class ToolExecutor:
    async def execute_with_fallback(self, tool_name: str, args: dict) -> str:
        """工具调用带兜底策略"""
        try:
            result = await asyncio.wait_for(
                self.tools[tool_name](**args),
                timeout=30.0            # 单个工具最多 30 秒
            )
            return str(result)
        except asyncio.TimeoutError:
            return "工具执行超时，请尝试简化参数"
        except Exception as e:
            # 让 LLM 知道失败了，可以换策略
            return f"工具执行失败: {type(e).__name__}，请尝试其他方法"
```

### 工具结果压缩
```python
def compress_tool_result(result: str, max_tokens: int = 2000) -> str:
    """长返回结果压缩，节省上下文窗口"""
    if len(result) <= max_tokens * 4:
        return result
    # 截断 + 提示
    return result[:max_tokens * 4] + "\n... (结果已截断，请缩小查询范围)"
```

---

## 总结检查清单

- [ ] 理解 Agent 的 ReAct 循环（Thought → Action → Observation）
- [ ] 能实现一个带工具调用的简单 Agent
- [ ] 知道多 Agent 协作的 4 种模式
- [ ] 理解 MCP 协议的基本概念（Tool / Resource / Prompt）
- [ ] 能说出 LangChain 和 LlamaIndex 的定位区别
- [ ] 能说出 LangChain 的 3 个优点和 3 个缺点
- [ ] 理解 LoRA/QLoRA 的核心思想
- [ ] 知道 Agent 执行中的常见问题：无限循环、工具超时、上下文溢出
