# 演示：把一篇运营笔记变成可检索知识

状态：根据代码编写的演示方案，尚未端到端执行。以下没有预制的 AI 输出，也没有实测耗时。

## 准备

使用你拥有使用权限、可发送给模型服务的短文本。首次演示建议选择自己写的运营复盘，并给出真实来源链接（没有链接可留空）。不要把假设案例包装成店铺实际效果。

使用仓库根目录的 compose.langgraph.yml；复制 .env.example 为 .env 并填写自己的模型配置，已有 .env 时不要覆盖。演示所需配置：

- Docker 和 Compose。
- python_api、vector_db，以及可选 frontend；本次不需要 n8n、飞书或隧道服务。
- 自己的 AI_API_KEY，以及可调用的 AI_MODEL（代码默认 deepseek-ai/DeepSeek-V3）。
- 支持 BAAI/bge-m3 的向量模型权限；当前默认向量维度为 1024。若文本与向量使用不同供应商，单独配置 EMBEDDING_API_KEY、EMBEDDING_BASE_URL、EMBEDDING_MODEL 和 EMBEDDING_VECTOR_SIZE。
- 后端的 QDRANT_URL 为 http://vector_db:6333。
- 独立的演示 Markdown 目录挂载到后端 /obsidian；不要把私人笔记库用于公开演示。

以下命令均在仓库根目录执行。CI 已验证镜像构建与无真实模型调用的服务启动；你自己的凭证与资料仍需按下文验收。先启动数据库，再启动后端：

```powershell
docker compose -f compose.langgraph.yml up -d vector_db
Invoke-RestMethod http://localhost:6333/collections
docker compose -f compose.langgraph.yml up -d --build python_api frontend
Invoke-RestMethod http://localhost:8000/health
```

数据库尚未就绪时先等待其启动；后端健康检查的 vector_db 应为 connected。仅有 status=healthy 不能证明模型凭证有效。

## 1. 提交原文

在 http://localhost:3000 打开「整理原文」，或在 http://localhost:8000/docs 打开 POST /api/process_content，填入：

- title：本次演示的唯一标题，避免覆盖同名笔记。
- url：真实来源链接，没有则留空。
- raw_text：你要整理的原文。

执行一次请求，保存实际返回的 summary、key_points、modules、tags 和 filepath。核对具体数字与建议是否能在原文找到依据；不要提前填写“理想答案”。

通过标准：请求成功，返回内容非空，原文事实没有被改写成不存在的结论。

## 2. 查看 Markdown

打开演示目录内生成的笔记，核对摘要、模块、标签和 source。记录原文到知识卡片的实际变化。

通过标准：文件确实存在，内容与接口输出对应；提供链接时，来源链接保留正确。

## 3. 建立索引

保存成功后点击页面顶部「建立 / 更新索引」，等待任务成功并显示片段数。失败后查看配置并重试，不需要重新整理已经保存的笔记。也可以在根目录运行以下命令，勿与网页索引同时执行：

```powershell
docker compose -f compose.langgraph.yml exec python_api python vector_indexer.py
```

这会索引挂载目录中的 Markdown，并调用付费或限额的向量接口。请只使用独立演示目录。

通过标准：任务或脚本完成且写入条数大于零。失败时保留脱敏后的真实错误，不跳过这一步宣布检索可用。

## 4. 检索并核对来源

在 API 文档中执行 POST /api/search_knowledge：

```json
{
  "query": "填写一个你的原文确实涉及的问题",
  "limit": 3
}
```

也可以打开 http://localhost:3000 的知识搜索页面。

通过标准：返回片段与问题相关，source_file 指向本次笔记；输入来源链接时，source_url 与它一致。score 是相似度，不是回答正确率。

再问一个原文完全未提及的问题，记录真实检索结果。当前接口按相似度返回片段，不能假定它会自动拒答。

## 5. 提问并核对回答

打开「知识问答」，输入一个原文能够回答的问题。核对回答中的事实与引用原文，确认来源指向本次笔记。再提问一个资料未覆盖的问题，记录 answered、insufficient_context 或 no_data 等实际状态；引用编号有效并不代表回答内容必然准确。

通过标准：有依据的问题回答可在原文核对；资料不足时明确说明，不捏造运营数据。错误凭证或服务不可用时显示真实失败，不生成成功结果。

## 录屏和记录

建议剪辑成 45–60 秒，展示原文、实际生成内容、Markdown、索引完成、来源检索。等待过程可以剪辑，但标明加速或删减，另附完整实际耗时。

| 验收项 | 实际结果 |
| --- | --- |
| 提交文本与真实来源 | 待填写 |
| 模型、运行日期、代码版本 | 待填写 |
| 整理耗时 / 索引耗时 / 检索耗时 | 待测量 |
| 保存文件与来源核对 | 待执行 |
| 检索命中与不相关问题表现 | 待执行 |
| 调用费用 | 待从供应商账单核对，无法核对则写未知 |

录屏前检查界面与终端，遮挡凭证、私人路径、账号和商业数据。请求正文日志已移除，公开演示仍只使用可公开的文本。
