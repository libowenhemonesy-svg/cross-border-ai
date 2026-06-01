# 🛒 跨境电商 AI 智能助手

> 基于 **n8n + Agent + RAG** 构建的跨境电商智能知识库问答系统

## 项目概述

将 16 份亚马逊运营专业文档（选品方法论、广告 ACOS 优化、FBA 库存管理、合规风控、Listing 优化等）构建为可语义检索的向量知识库，通过 **AI Agent** 自主决策检索与生成，为运营团队提供 SOP 级准确回答。

## 技术架构

```
用户提问 → Chat Trigger
         → AI Agent (DeepSeek / OpenAI 兼容)
            ├─ Window Buffer Memory (10轮上下文)
            └─ 知识库检索工具 (向量相似度 Top-K=4)
               └─ Obsidian Vault (16篇专业文档)
                  → Text Splitter (1000/100)
                  → Ollama Embeddings (nomic-embed-text)
                  → In-Memory Vector Store
         → 结构化答案 + 来源引用
```

## 项目结构

```
├── docker-compose.yml                  # 开源版 n8n Docker 部署配置
├── data_extractors/                    # 跨平台内容抓取服务（Python）
│   └── requirements.txt                # FastAPI + httpx + yt-dlp + openai
├── my_agent/                           # LangGraph 智能 Agent 模块
├── langgraph.json                      # LangGraph CLI 配置
├── langgraph_demo.py                   # LangGraph 示例
├── scrapling_demo.py                   # Scrapling 网页抓取演示
├── scrapling_入门.py                    # Scrapling 入门教程
├── agentic-rag-workflow.json          # Agentic RAG 主工作流（n8n）
├── obsidian-fix-v3.json               # Obsidian → 向量库 数据注入管道
├── exported-rag.json / fixed-rag.json # RAG 工作流历史版本
├── verify.json                        # 验证工作流
├── *.js                               # n8n 工作流维护脚本
│   ├── final-switch-to-openai.js      # 模型切换脚本 (DeepSeek → OpenAI)
│   ├── create-deepseek-cred.js        # 凭证创建脚本
│   ├── fix-agent-text.js              # Agent Prompt 直接修改脚本
│   ├── fix-prompt.js                  # Agent Prompt 修复脚本
│   └── add-code-node.js               # 注入管道节点添加脚本
├── fix-workflow.sql                   # SQL 级工作流修复
├── 亚马逊/                              # Obsidian 知识库（16篇专业文档）
│   ├── 亚马逊选品实战方法论.md
│   ├── 亚马逊广告ACOS优化实战.md
│   ├── 亚马逊FBA库存管理.md
│   ├── 亚马逊Listing优化完全指南.md
│   └── ...
├── ai/ai知识/                          # AI应用工程师面试知识体系
│   ├── AI知识点详解.md                  # 12章纯知识点（概念/原理/选型）
│   ├── 面试题参考答案.md                 # 20道高频面试题详解
│   ├── 01-07*.md                      # 分模块详细教程
│   └── 面试题.md / 李博文.md           # 个人评估
└── README.md
```

## 快速开始

### 环境要求

- Docker Desktop（推荐）或 Node.js ≥ 20
- n8n (≥ v1.0) + LangChain 节点
- Ollama (本地 Embedding 模型)
- Obsidian + Local REST API 插件
- DeepSeek API Key 或兼容 OpenAI 接口的国内模型（硅基流动、阿里云百炼等）

### 部署 n8n

```bash
# 方式一：Docker Compose（推荐，数据持久化）
docker compose up -d

# 方式二：Docker 命令行
docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

访问 `http://localhost:5678` 完成初始化设置。

### 安装 Python 依赖

```bash
pip install -r data_extractors/requirements.txt
```

### 导入工作流

1. 在 n8n 中导入 `agentic-rag-workflow.json`
2. 配置凭证（DeepSeek / OpenAI API Key）
3. 导入 `obsidian-fix-v3.json` 并运行一次注入知识库
4. 启动 Chat Trigger，开始对话

## 知识库覆盖领域

| # | 文档 | 核心内容 |
|---|------|---------|
| 1 | 选品实战方法论 | 市场容量分析、竞品调研、利润测算 |
| 2 | 广告 ACOS 优化 | 广告架构、竞价策略、ACOS 控制 |
| 3 | FBA 库存管理 | 补货策略、库存周转、IPI 优化 |
| 4 | Listing 优化 | 标题/五点/描述/A+ 优化方法 |
| 5 | 合规风控与账号安全 | 账号健康、知识产权、评论合规 |
| 6 | 竞品分析方法论 | 竞品调研框架、数据采集、SWOT |
| 7 | 供应链与 1688 采购 | 供应商筛选、采购流程、物流 |
| 8 | 品牌注册与保护 | Brand Registry、透明计划 |
| 9 | 关键词调研 | 搜索词挖掘、长尾词策略 |
| 10 | 站外引流 | SNS、Deal 站、KOL 合作 |
| 11 | 财务管理与利润核算 | 成本结构、利润表、税务 |
| 12 | 新品广告预算分配 | 新品期广告投放策略 |
| 13 | 跨境电商入门指南 | 注册、上架、物流全流程 |
| 14 | 亚马逊官网总览 | 平台功能概览 |
| 15 | 全球开店 | 多站点运营策略 |
| 16 | AWS 云服务概览 | AWS 核心服务介绍 |

## 技术亮点

- **Agent 自主决策**：AI 自动判断何时检索知识库、何时直接回答，避免无意义检索
- **Vector + 关键词混合检索**：确保专有名词和精确术语的命中率
- **数据注入管道**：Obsidian API → URL 编码 → 分块 → 向量化 → 存储，全自动
- **直接 SQLite 维护**：绕过 n8n UI 的复杂操作，脚本直接更新工作流配置
- **错误告警**：管道异常自动推送 Slack 通知
- **凭证安全**：所有敏感信息已使用占位符替换
