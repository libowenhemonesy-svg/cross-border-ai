const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');
const DB = '/home/node/.n8n/database.sqlite';
const WORKFLOW_ID = 'f62db897-0ebb-4987-803e-224abb5d9feb';

const db = new sqlite3.Database(DB);

db.get("SELECT nodes, connections FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err, row) => {
  if (err) { console.error(err); process.exit(1); }
  const nodes = JSON.parse(row.nodes);
  const connections = JSON.parse(row.connections);

  const oldNames = ['DeepSeek Chat Model', 'DeepSeek Chat Model1'];
  const newNames = ['DeepSeek Chat Model (Agent)', 'DeepSeek Chat Model (Tool)'];

  for (let i = 0; i < oldNames.length; i++) {
    const node = nodes.find(n => n.name === oldNames[i]);
    if (!node) { console.log('Node not found:', oldNames[i]); continue; }

    node.name = newNames[i];
    node.type = '@n8n/n8n-nodes-langchain.lmChatOpenAi';
    node.typeVersion = 1.3;
    node.parameters = {
      model: { mode: 'id', value: 'deepseek-chat' },
      options: {
        baseURL: 'https://api.deepseek.com/v1',
        temperature: i === 0 ? 0.7 : 0.3,
        maxTokens: 4096
      }
    };
    node.credentials = {
      openAiApi: {
        id: 'f9acd031-05fc-4611-b4c1-758a5af8e552',
        name: 'DeepSeek API (OpenAI Compat)'
      }
    };

    if (connections[oldNames[i]]) {
      connections[newNames[i]] = connections[oldNames[i]];
      delete connections[oldNames[i]];
    }
    for (const [src, srcConns] of Object.entries(connections)) {
      for (const [, typeValues] of Object.entries(srcConns)) {
        if (!typeValues) continue;
        for (const subArr of typeValues) {
          if (!subArr) continue;
          for (const conn of subArr) {
            if (conn.node === oldNames[i]) conn.node = newNames[i];
          }
        }
      }
    }
    console.log('Switched:', oldNames[i], '→', newNames[i]);
  }

  // 确保 promptType: define + 完整提示词
  for (const node of nodes) {
    if (node.type && node.type.includes('agent')) {
      node.parameters.promptType = 'define';
      node.parameters.text = '你是一名资深的跨境电商运营专家和AI助手。\n\n核心能力：\n1. 亚马逊运营规范：Listing优化、广告投放、库存管理等全链路SOP\n2. ERP发补货流程：FBA补货策略、库存周转计算、供应链异常处理\n3. 亚马逊政策红线：账号健康、知识产权、评论合规\n4. 选品分析方法论：市场容量、竞品调研、利润测算\n\n重要规则：\n- 当用户询问公司内部规范/SOP/政策时，必须使用知识库检索工具查找权威信息\n- 基于检索到的上下文给出精准回答，无相关信息时诚实告知\n- 使用中文回复，以分点或表格组织信息';
      console.log('Agent promptType: define (完整版)');
    }
  }

  db.run('UPDATE workflow_entity SET nodes = ?, connections = ?, updatedAt = ? WHERE id = ?',
    [JSON.stringify(nodes), JSON.stringify(connections), new Date().toISOString(), WORKFLOW_ID],
    function(err2) {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('Done. Rows:', this.changes);
      for (const n of nodes) console.log(n.name, '|', n.type);
      db.close();
    });
});
