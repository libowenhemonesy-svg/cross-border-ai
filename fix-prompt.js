const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');
const DB = '/home/node/.n8n/database.sqlite';

const db = new sqlite3.Database(DB);

db.get("SELECT nodes FROM workflow_entity WHERE id = ?", ['f62db897-0ebb-4987-803e-224abb5d9feb'], (err, row) => {
  if (err) { console.error(err); process.exit(1); }
  const nodes = JSON.parse(row.nodes);

  for (const node of nodes) {
    if (node.name === 'AI Agent') {
      node.parameters.promptType = 'define';
      node.parameters.text = '你是一名资深的跨境电商运营专家和AI助手。\n\n核心能力：\n1. 亚马逊运营规范：Listing优化、广告投放、库存管理等全链路SOP\n2. ERP发补货流程：FBA补货策略、库存周转计算、供应链异常处理\n3. 亚马逊政策红线：账号健康、知识产权、评论合规\n4. 选品分析方法论：市场容量、竞品调研、利润测算\n\n重要规则（必须严格遵守）：\n- 无论用户询问什么，你都必须首先调用"知识库检索工具"检索公司知识库\n- 即使问题看起来是通用知识，也必须先检索知识库，因为公司有特定的内部规范和流程\n- 基于检索到的上下文给出精准回答，如果知识库中没有相关信息，请诚实告知"未在知识库中找到相关信息"，然后可以补充你的通用知识\n- 回答时引用知识库中的具体数据或规定，保持专业、清晰、结构化的回答风格\n- 使用中文回复，适当使用分点或表格组织信息\n\n工作流程：\n1. 收到用户问题 → 立即调用知识库检索工具\n2. 获取检索结果 → 基于结果组织回答\n3. 如无结果 → 诚实告知 + 补充通用建议';
      console.log('Fixed: AI Agent prompt');
    }

    if (node.name === '知识库检索工具') {
      node.parameters.description = '这是公司内部知识库，包含所有跨境电商相关的标准操作流程(SOP)、政策规范、选品方法论、ERP操作指南等权威文档。收到任何与跨境电商、亚马逊运营、选品分析、ERP流程相关的问题时，都必须优先使用此工具检索。输入应为完整的中文检索问句。';
      console.log('Fixed: 知识库检索工具 description');
    }

    if (node.name === 'Chat Trigger') {
      node.parameters.initialMessage = '你好！我是跨境电商业务助手。请直接提出你的问题，我会从公司知识库中检索最准确的答案。';
      console.log('Fixed: Chat Trigger initialMessage');
    }
  }

  db.run('UPDATE workflow_entity SET nodes = ?, updatedAt = ? WHERE id = ?',
    [JSON.stringify(nodes), new Date().toISOString(), 'f62db897-0ebb-4987-803e-224abb5d9feb'],
    function(err2) {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('QA Agent DB updated. Rows:', this.changes);
      db.close();
    });
});
