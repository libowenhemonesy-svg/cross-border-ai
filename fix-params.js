const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');

const DB = '/home/node/.n8n/database.sqlite';
const WORKFLOW_ID = 'f62db897-0ebb-4987-803e-224abb5d9feb';

const db = new sqlite3.Database(DB);

db.get("SELECT nodes, connections, settings FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err, row) => {
  if (err) { console.error(err); process.exit(1); }

  const nodes = JSON.parse(row.nodes);
  let fixed = 0;

  for (const node of nodes) {
    if (node.type.includes('memoryBufferWindow')) {
      if (!node.parameters.sessionKey) {
        node.parameters.sessionKey = "={{ $json.sessionId }}";
        console.log('Fixed: Window Buffer Memory → sessionKey');
        fixed++;
      }
    }
    if (node.type.includes('vectorStoreInMemory')) {
      if (!node.parameters.mode) {
        node.parameters.mode = "retrieve";
        console.log('Fixed: Vector Store → mode: retrieve');
        fixed++;
      }
    }
    if (node.type.includes('toolVectorStore')) {
      if (!node.parameters.topK) {
        node.parameters.topK = 4;
        console.log('Fixed: 知识库检索工具 → topK: 4');
        fixed++;
      }
    }
    if (node.type.includes('chatTrigger')) {
      if (typeof node.parameters.public === 'undefined') {
        node.parameters.public = false;
        node.parameters.initialMessage = "你好！我是跨境电商业务助手。\n\n我可以帮你查询：\n- 亚马逊运营SOP规范\n- ERP发补货流程\n- 亚马逊政策红线\n- 选品分析方法论\n\n请直接提问，我会从公司知识库中检索最准确的答案。";
        console.log('Fixed: Chat Trigger → public + initialMessage');
        fixed++;
      }
    }
  }

  console.log('Total fixes:', fixed);

  const nodesJson = JSON.stringify(nodes);
  const now = new Date().toISOString();

  db.run('UPDATE workflow_entity SET nodes = ?, updatedAt = ? WHERE id = ?',
    [nodesJson, now, WORKFLOW_ID],
    function(err2) {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('DB updated, rows:', this.changes);

      // Verify
      db.get("SELECT nodes FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err3, row2) => {
        const verified = JSON.parse(row2.nodes);
        for (const n of verified) {
          console.log(n.name, '→', JSON.stringify(n.parameters));
        }
        db.close();
      });
    });
});
