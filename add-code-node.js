const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');

const DB = '/home/node/.n8n/database.sqlite';
const WORKFLOW_ID = 'weO4PVHvGHCoLwFx';

const db = new sqlite3.Database(DB);

db.get("SELECT nodes, connections FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err, row) => {
  if (err) { console.error(err); process.exit(1); }

  const nodes = JSON.parse(row.nodes);
  const connections = JSON.parse(row.connections);

  // 1. 添加 Code Format Data 节点
  const codeNode = {
    parameters: {
      jsCode: [
        '// 将 HTTP 响应中的原始文本转换为 Vector Store 所需的文档格式',
        'const items = $input.all();',
        'for (const item of items) {',
        '  // 提取原始文本：可能是 string 或含 response/data 字段的对象',
        '  let rawText = "";',
        '  if (typeof item.json === "string") {',
        '    rawText = item.json;',
        '  } else if (item.json.response) {',
        '    rawText = item.json.response;',
        '  } else if (item.json.data) {',
        '    rawText = typeof item.json.data === "string" ? item.json.data : JSON.stringify(item.json.data);',
        '  } else {',
        '    rawText = JSON.stringify(item.json);',
        '  }',
        '  // 构造 Default Data Loader (N8nJsonLoader) 期望的格式',
        '  item.json = {',
        '    pageContent: rawText,',
        '    metadata: {',
        '      source: "obsidian-vault",',
        '      ingestedAt: new Date().toISOString()',
        '    }',
        '  };',
        '}',
        'return items;'
      ].join('\n')
    },
    id: 'c0000001-e001-4000-c001-000000000001',
    name: 'Code Format Data',
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position: [1560, 300]
  };

  // 找到 Vector Store 的旧位置，把 Code 节点放在 HTTP Fetch File 和 Vector Store 之间
  const httpFetchNode = nodes.find(n => n.name === 'HTTP Fetch File');
  const vectorStoreNode = nodes.find(n => n.name === 'Vector Store');

  if (httpFetchNode && vectorStoreNode) {
    // Code 节点放在两者 X 坐标中间
    codeNode.position = [
      Math.round((httpFetchNode.position[0] + vectorStoreNode.position[0]) / 2),
      httpFetchNode.position[1]
    ];
  }

  nodes.push(codeNode);
  console.log('Added node: Code Format Data at', codeNode.position);

  // 2. 修改连接：HTTP Fetch File → Code Format Data → Vector Store
  // 把 HTTP Fetch File 的 main 输出指向 Code Format Data
  const fetchConn = connections['HTTP Fetch File'];
  if (fetchConn && fetchConn.main && fetchConn.main[0]) {
    for (const conn of fetchConn.main[0]) {
      if (conn.node === 'Vector Store') {
        conn.node = 'Code Format Data';
        console.log('Re-routed: HTTP Fetch File → Code Format Data');
      }
    }
  }

  // 添加 Code Format Data → Vector Store 的连接
  connections['Code Format Data'] = {
    main: [
      [
        {
          node: 'Vector Store',
          type: 'main',
          index: 0
        }
      ]
    ]
  };
  console.log('Added connection: Code Format Data → Vector Store');

  // 3. 同步更新 obsidian-fix-v3.json 中的 URL（HTTPS→HTTP）
  for (const node of nodes) {
    if (node.name === 'HTTP Get Vault List' && node.parameters.url) {
      const old = node.parameters.url;
      node.parameters.url = node.parameters.url.replace('https://host.docker.internal:27124', 'http://host.docker.internal:27123');
      if (old !== node.parameters.url) console.log('Fixed URL: HTTP Get Vault List');
    }
    if (node.name === 'HTTP Fetch File' && node.parameters.url) {
      const old = node.parameters.url;
      node.parameters.url = node.parameters.url.replace('https://host.docker.internal:27124', 'http://host.docker.internal:27123');
      if (old !== node.parameters.url) console.log('Fixed URL: HTTP Fetch File');
    }
    // 修复 Split Out Items 的 include 参数
    if (node.name === 'Split Out Items' && node.parameters.include === 'noOtherFields') {
      delete node.parameters.include;
      console.log('Fixed: Split Out Items → removed noOtherFields');
    }
  }

  // 4. 写入数据库
  db.run(
    'UPDATE workflow_entity SET nodes = ?, connections = ?, updatedAt = ? WHERE id = ?',
    [JSON.stringify(nodes), JSON.stringify(connections), new Date().toISOString(), WORKFLOW_ID],
    function(err2) {
      if (err2) { console.error(err2); process.exit(1); }
      console.log('Database updated. Rows affected:', this.changes);

      // 验证
      db.get("SELECT id, name, substr(nodes, 1, 200) as preview FROM workflow_entity WHERE id = ?", [WORKFLOW_ID], (err3, row2) => {
        if (err3) { console.error(err3); process.exit(1); }
        console.log('Verified:', row2.name);
        console.log('Nodes in workflow:');
        const verified = JSON.parse(row2.nodes);
        for (const n of verified) {
          console.log(' -', n.name, '|', n.type);
        }
        console.log('\nConnections from HTTP Fetch File:', JSON.stringify(connections['HTTP Fetch File']));
        console.log('Connections from Code Format Data:', JSON.stringify(connections['Code Format Data']));
        db.close();
      });
    }
  );
});
