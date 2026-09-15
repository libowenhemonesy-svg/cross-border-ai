# LangGraph 知识问答

知识库问答主流程已从固定内容的 LangGraph 示例替换为真实检索和模型调用，并接入现有 Web 控制台。此路径不需要 n8n。

执行图：START → retrieve → answer / no_data → END。

- retrieve：复用 Qdrant 检索，给每个原文片段添加来源编号。
- answer：调用真实模型，校验返回结构以及引用编号是否属于本次检索结果。
- no_data：没有结果时返回明确的无数据状态，不调用模型。
- 资料不足时允许模型返回 insufficient_context；调用失败返回 HTTP 502，缺少配置或检索未就绪返回 503。

引用编号校验只保证编号存在，不能证明模型回答完全忠实原文。模型仍需实测评估。当前为单轮问答，不保留聊天历史，也不提供持久化记忆。

## 独立启动

在仓库根目录执行。先复制 .env.example 为 .env，填写你自己的 AI_API_KEY。默认问答、内容整理和向量模型均使用硅基流动，需要账户有对应模型调用权限。

AI_BASE_URL 同时用于知识问答与内容整理。向量模型使用独立的 EMBEDDING_BASE_URL、EMBEDDING_MODEL 和 EMBEDDING_VECTOR_SIZE；EMBEDDING_API_KEY 留空时沿用 AI_API_KEY。默认向量服务仍为硅基流动，切换文本模型供应商时应为向量服务单独提供凭证。已有集合的维度必须与配置一致。

```powershell
Copy-Item .env.example .env
# 编辑 .env 填写配置，再启动数据库。
docker compose -f compose.langgraph.yml up -d vector_db
Invoke-RestMethod http://localhost:6333/collections
# 数据库就绪后再启动后端和页面。
docker compose -f compose.langgraph.yml up -d --build python_api frontend
Invoke-RestMethod http://localhost:8000/health
```

已有 .env 时跳过复制，直接编辑，避免覆盖本地配置。上述 Copy-Item 仅用于首次配置。

服务绑定本机，未提供公共访问鉴权，不要直接暴露到公网。此独立配置不读取旧 Compose 内的凭证，不启动 n8n、飞书推送或隧道。

先打开 http://localhost:3000 的「整理原文」，填写唯一标题、可选来源链接和正文，提交生成知识卡片。也可以通过 http://localhost:8000/docs 的 /api/process_content 提交，或将自己的 Markdown 放进 runtime/obsidian。模型会接收提交的内容；请只使用你有权发送给供应商的资料。请求正文不再写入中间件日志。

在网页上点击「建立 / 更新索引」，页面会显示运行中、成功片段数或失败提示。保存新笔记后需再次更新索引；失败可直接重试。也可以手动执行：

```powershell
docker compose -f compose.langgraph.yml exec python_api python vector_indexer.py
```

打开 http://localhost:3000，选择「知识问答」。输入问题后可以看到回答、检索原文、来源链接和引用标记。

也可直接调用：

```powershell
$askBody = @{ question = "你的笔记里关于广告优化有哪些步骤？" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/ask_knowledge -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($askBody))
```

如启动时向量服务不可用，恢复服务后重新检索或建立索引，后端会再次尝试初始化，无需重启。网页索引接口为 POST /api/knowledge/index（202），状态查询为 GET /api/knowledge/index。

索引任务状态保存在进程内，服务重启后回到 idle；当前独立部署使用单进程，同一进程中的重复点击不会启动第二个任务。不要同时执行网页索引与 CLI 索引，或将此任务接口部署成多 worker。文档新分块确认写入后才清理该文档的旧分块；向量化失败时保留原索引。空文档、读取失败和已删除的本地文件不会自动清除既有知识。

### 子文件夹笔记

索引会读取挂载目录及其子目录中的 `.md` 文件。来源保留相对路径，例如 `广告/note.md` 和 `选品/note.md`，同名文件不会互相覆盖。根目录已有笔记继续使用原索引标识，无需重建集合。隐藏文件和隐藏目录（例如 `.trash`）不参与索引，符号链接文件及解析到知识库之外的路径也不会读取。

## CLI / Studio

CLI 与 Studio 通过 KNOWLEDGE_API_URL 调用已有的 /api/search_knowledge，再执行同一套 LangGraph 问答逻辑。它们不需要 n8n，但需要已启动且已索引的后端。

在已激活的 Python 虚拟环境中安装根目录依赖：

```powershell
python -m pip install -r requirements.txt
python langgraph_demo.py "你的问题"
```

CLI 从进程环境读取 AI_API_KEY、AI_BASE_URL、AI_MODEL 和 KNOWLEDGE_API_URL，不会自动加载 .env。Studio 配置继续使用 langgraph.json，读取 .env，图入口为 my_agent/graph.py:app；输入格式为 {"question": "你的问题"}，旧的 messages/step_count 示例输入不再适用。

## 迁移范围与验证

本次替换知识问答主路径和原有固定天气示例，增加 API、Web 入口、独立部署配置与离线测试。历史 n8n JSON 保留供参考，已有视频采集、飞书、日报调度未迁移。

测试显式注入检索和模型替身，不调用付费接口：

```powershell
python -m pip install pytest fastapi httpx
python -m pytest tests/test_rag.py -q
```

完整后端回归需安装 gangweiceshi/data_extractors/requirements.txt，然后运行 python -m pytest tests -q。独立环境、浏览器、44 项测试及 Docker 启动检查的记录见 [验收记录](validation.md)。

未配置真实密钥、未在 Docker 环境执行时，不能将这些离线测试描述为完整功能验收。端到端需验证：导入 → 索引 → 提问 → 原文核对；并测试无资料、无关资料与错误凭证。

图编排使用 LangGraph 官方 StateGraph 与条件边接口：
https://docs.langchain.com/oss/python/langgraph/graph-api
