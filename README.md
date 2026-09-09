# 跨境电商 AI 全能助手 · Cross-border AI

让运营知识随问随用，让重复工作自动完成。

面向跨境运营的 AI 工作台，包含知识问答、内容整理与日报工作流。知识问答基于 LangGraph，从检索资料到生成回答，支持查看参考原文；资料不足时明确告知。

当前重点：知识问答与内容整理。更多运营能力持续完善中。开发预览版，尚未完成干净环境下的端到端部署验收。

[本地部署](docs/langgraph.md) · [演示步骤](docs/demo.md) · [反馈问题](https://github.com/libowenhemonesy-svg/cross-border-ai/issues)

- 整理笔记：将原文提炼为摘要、要点和标签，保存为 Markdown 知识卡片。
- 提问找答案：使用 LangGraph 检索已索引资料，调用模型生成回答，问答主路径无需 n8n。
- 核对来源：查看检索原文与引用编号，回到来源核对回答依据。

## 先看一个具体场景

你有一篇广告优化笔记，希望下次遇到相似问题时能找回来：

1. 提交原文：后端调用真实模型，提取摘要、模块化要点和标签。
2. 保存笔记：生成 Obsidian 兼容 Markdown，保留输入的来源链接。
3. 建立索引：手动运行向量索引脚本，把笔记写入 Qdrant。
4. 检索知识：输入问题，返回相关文本、来源文件、来源链接和相似度。

检索接口返回原文片段；新增问答接口 /api/ask_knowledge 使用 LangGraph 调用模型回答，并返回来源。无资料或调用失败会明确告知。尚无广告效果、收益提升或回答准确率的实测承诺。

## 仓库里有什么

| 模块 | 代码入口 | 当前边界 |
| --- | --- | --- |
| LangGraph 问答 | [rag_graph.py](gangweiceshi/data_extractors/rag_graph.py) | 检索、无资料分支、真实模型回答、来源编号校验；单轮问答 |
| 内容整理 API | [main.py](gangweiceshi/data_extractors/main.py) | 文本整理、B 站/微信处理、日报、检索接口 |
| AI 知识卡片 | [ai_processor.py](gangweiceshi/data_extractors/ai_processor.py) | 默认使用硅基流动接口；需要自己的有效模型凭证 |
| Markdown 保存 | [obsidian_writer.py](gangweiceshi/data_extractors/obsidian_writer.py) | 保存到本地挂载目录；文本整理路径无需 Obsidian REST 插件 |
| 向量检索 | [vector_indexer.py](gangweiceshi/data_extractors/vector_indexer.py) | BGE-M3 + Qdrant；文本整理后须另行建索引 |
| Web 控制台 | [frontend](gangweiceshi/frontend/) | React 页面，包含内容处理、日报与搜索入口 |
| n8n 问答实验 | [工作流](agentic-rag-workflow.json) | 独立的问答工作流；不要与 Qdrant 后端视为同一条已接通链路 |
| Amazon 浏览器扩展 | [扩展目录](amazon-ai-product-analyzer/) | 提取商品信息，并请求本机 8010 端口的另一后端；不属于本次演示 |
| 运营笔记 | [亚马逊](亚马逊/) | 仓库附带参考资料，使用前应核对来源与时效 |

## 从哪里开始

先阅读 [LangGraph 启动说明](docs/langgraph.md)，使用根目录 compose.langgraph.yml 和自己的环境配置。基础资料整理的验收步骤见 [演示说明](docs/demo.md)。

部署文件实际位于 [gangweiceshi/docker-compose.yml](gangweiceshi/docker-compose.yml)，Python 依赖位于 [gangweiceshi/data_extractors/requirements.txt](gangweiceshi/data_extractors/requirements.txt)，都不在仓库根目录。

现有部署配置和历史工作流需要先清理凭证配置，并使用你自己的凭证。请勿直接使用仓库内的配置值。首次部署须核对服务配置、模型权限及存储挂载；当前不提供“一键部署已验证”的保证。

默认代码中，文本模型与向量模型使用硅基流动接口。兼容 OpenAI 协议不代表只更换 Key 就能切换任意供应商。

## 已知限制

- LangGraph 问答已覆盖离线图执行及 API 测试；尚未验证真实模型请求、容器构建或完整演示。
- 健康检查不能证明模型可用或知识库已经建立；需要分别验收。
- 抓取能力受页面变化、登录状态及外部服务可用性影响。
- 根目录仍保留历史工作流与维护脚本，不是推荐部署步骤。
- 历史文件中发现疑似明文凭证；维护者需要撤销或轮换，并检查历史记录。删除当前文件里的值不能使旧凭证失效。
- 尚未在仓库根目录提供统一许可证；子目录中的许可证描述不应视为覆盖整个仓库。

## 下一次更新

- [ ] 清理凭证配置，补充无真实密钥的配置样例。
- [ ] 在干净环境跑通文本整理、保存、索引和检索。
- [ ] 发布一段真实录屏及可核对的输入、输出、耗时。
- [ ] 增加来源匹配、无依据问题和模型失败的评测记录。
- [ ] 明确全仓库许可证及依赖、资料的使用边界。

欢迎提交带有复现步骤的 Issue：使用的功能、预期行为、实际行为、脱敏后的错误信息。请勿附带 API Key、Cookie 或私人运营数据。
