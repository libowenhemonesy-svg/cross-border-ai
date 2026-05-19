const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');
const fs = require('fs');

const DB = '/home/node/.n8n/database.sqlite';
const WORKFLOW_ID = 'f62db897-0ebb-4987-803e-224abb5d9feb';
const FIXED_JSON = '/tmp/fixed-rag.json';

const wf = JSON.parse(fs.readFileSync(FIXED_JSON, 'utf8'));

const nodes = JSON.stringify(wf.nodes);
const connections = JSON.stringify(wf.connections);
const settings = JSON.stringify(wf.settings);
const now = new Date().toISOString();

const db = new sqlite3.Database(DB);

db.run(
  `UPDATE workflow_entity SET nodes = ?, connections = ?, settings = ?, updatedAt = ? WHERE id = ?`,
  [nodes, connections, settings, now, WORKFLOW_ID],
  function(err) {
    if (err) { console.error('Update error:', err); process.exit(1); }
    console.log('Rows updated:', this.changes);

    // Verify
    db.get("SELECT name, substr(nodes, 1, 100) as nodes_preview FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err2, row) => {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('Verified workflow:', row.name);
      db.close();
    });
  }
);
