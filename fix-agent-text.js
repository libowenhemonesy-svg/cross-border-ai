const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');
const DB = '/home/node/.n8n/database.sqlite';
const WORKFLOW_ID = 'f62db897-0ebb-4987-803e-224abb5d9feb';

// The expression for define mode: combines system prompt + user's chatInput
const TEXT_EXPR = "={{ '你是一名资深的跨境电商运营专家。\\n\\n核心规则：\\n- 必须先调用知识库检索工具查找公司内部知识库\\n- 基于检索结果回答，如果知识库中没有相关信息，诚实说明\\n- 中文回复，用分点或表格组织信息\\n\\n用户问题：' + $json.chatInput }}";

const db = new sqlite3.Database(DB);

db.get("SELECT nodes FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err, row) => {
  if (err) { console.error(err); process.exit(1); }
  const nodes = JSON.parse(row.nodes);

  for (const node of nodes) {
    if (node.type && node.type.includes('agent')) {
      node.parameters.promptType = 'define';
      node.parameters.text = TEXT_EXPR;
      console.log('Agent text set to:', node.parameters.text);
    }
  }

  db.run('UPDATE workflow_entity SET nodes = ?, updatedAt = ? WHERE id = ?',
    [JSON.stringify(nodes), new Date().toISOString(), WORKFLOW_ID],
    function(err2) {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('Done. Rows:', this.changes);
      db.close();
    });
});
