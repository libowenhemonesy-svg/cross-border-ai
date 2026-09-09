# 本地验收记录 · 2026-09-08

项目：跨境电商 AI 全能助手。范围：当前本地副本，尚未提交、推送或发布。

## 已完成

- 新增前端「整理原文」入口，可提交标题、来源和正文，展示知识卡片；清楚提示保存不等于完成索引。
- 浏览器实测必填校验、真实 API 缺少密钥的错误提示通过；未出现虚假保存成功状态。
- 模型模块、要点与标签类型校验加入回归，阻止畸形数据传到结果页面。

- 独立 Python 虚拟环境安装完整后端依赖成功，pip check 通过。当前验证环境为 Windows / Python 3.14，不代表 Docker Linux 环境已验收。
- 离线与本地集成测试：34 项通过。覆盖 LangGraph、真实 FastAPI 路由、内容失败不保存、原文保存、本地 Qdrant 索引及来源检索；模型与 Embedding 使用显式测试替身，无付费请求。
- 前端 TypeScript/Vite 生产构建：通过。存在未检测到 Tailwind 工具类的非阻断警告。
- 浏览器：使用本机 Edge 无头模式访问开发服务器，确认页面挂载、知识问答页切换、空问题校验通过，无 JavaScript 页面异常。
- 真实前后端联调（无模型凭证）：页面显示红色 degraded，提问显示未配置 AI_API_KEY，不显示假回答；尚未验证成功的真实模型回答。
- 修复内容提取异常被保存为“成功知识卡片”的问题；模型调用或摘要格式失败时明确报错、不保存。
- 移除请求正文及生成摘要日志；缺少模型配置时跳过向量服务初始化。
- 修复索引批次失败仍报告成功的问题；向量数量、维度不匹配时阻止本次写入。
- 补充前后端 Docker 构建排除规则，前端使用 npm ci 与锁文件安装依赖。
- 修复验收中发现的入口问题：此前 index.html 只加载 App.tsx，未调用 createRoot；新增 main.tsx 完成挂载。
- 名称：README、网页标题、侧栏与发布材料同步为“跨境电商 AI 全能助手”。
- 本地凭证清理：旧 Compose 的模型 Key 和飞书 Webhook 改为环境变量；obsidian-fix-v2/v3 工作流的 Bearer 值改为占位符。
- 目标业务文本文件复查：未发现所扫描的长 Bearer、sk- Key、飞书机器人 Webhook 模式。该模式检查并非完整密钥审计；第三方插件打包文件和 Git 历史未纳入清理。

## 未完成及原因

- Docker 全新环境部署：本机未找到 Docker 命令或标准 Docker Desktop 可执行文件。
- 真实模型调用与 Embedding：副本没有 .env，当前进程未配置 AI_API_KEY；没有使用仓库中疑似泄露的旧凭证。
- 导入 → 索引 → 问答 → 原文核对：等待上述环境条件，不将离线测试当成真实链路成功。
- 真实问答录屏：等待真实链路跑通，未制作虚构输出。
- 凭证失效：仅清理本地当前文件，旧凭证仍需在对应服务撤销或轮换；远程仓库和历史记录未修改。
- 许可证：需维护者确认代码与资料权利范围及许可选择，未代选。

## 继续验收所需条件

1. 安装并启动 Docker Desktop。
2. 在副本根目录按 .env.example 配置自己的模型凭证，勿把密钥发进聊天。默认链路需要硅基流动文本模型与 BGE-M3 权限。
3. 选用一篇可公开、允许发送到模型服务的原文，按 langgraph.md 完成导入、索引和问答。
4. 核对实际回答与来源，再录屏并填写耗时；确认许可证后整理发布。

运行命令、模型配置边界和端口见 [LangGraph 启动说明](langgraph.md)。

## 本地测试复现

默认 pytest 只收集 tests 目录，避免自动运行旧的外部服务测试脚本。Windows 上本次遇到系统临时目录权限问题，改用仓库 runtime 下的全新目录后通过：

```powershell
New-Item -ItemType Directory -Path runtime -Force | Out-Null
$testTemp = Join-Path (Get-Location) ('runtime/pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests -q --basetemp $testTemp
.\.venv\Scripts\python.exe -m pip check
```

保留 FastAPI on_event 与第三方测试客户端的弃用警告；未为消除警告重构无关启动流程。
