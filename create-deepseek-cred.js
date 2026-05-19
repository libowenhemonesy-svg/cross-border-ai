// 在 n8n 容器内运行，解密现有 DeepSeek 凭证并创建 openAiApi 类型凭证
const { Container } = require('@n8n/db');
const { Cipher } = require('n8n-core');

async function main() {
  const config = require('/home/node/.n8n/config');
  const cipher = new Cipher({ encryptionKey: config.encryptionKey });

  // 从数据库读取所有凭证
  const db = require('better-sqlite3')('/home/node/.n8n/database.sqlite');
  const rows = db.prepare("SELECT id, name, type, data FROM credentials_entity").all();

  console.log("=== 现有凭证 ===");
  for (const row of rows) {
    if (row.data) {
      try {
        const decrypted = cipher.decrypt(row.data);
        console.log(`ID: ${row.id}`);
        console.log(`名称: ${row.name}`);
        console.log(`类型: ${row.type}`);
        console.log(`解密数据: ${decrypted}`);
        console.log("---");
      } catch (e) {
        console.log(`ID: ${row.id}, 名称: ${row.name}, 类型: ${row.type}, 解密失败: ${e.message}`);
        console.log("---");
      }
    }
  }

  // 找 deepSeekApi 凭证
  const deepseekCred = rows.find(r => r.type === 'deepSeekApi');
  if (deepseekCred) {
    const decrypted = cipher.decrypt(deepseekCred.data);
    console.log("=== 找到 DeepSeek 凭证 ===");
    console.log("解密数据:", decrypted);

    // 解析 JSON
    let apiKey, baseUrl;
    try {
      const parsed = JSON.parse(decrypted);
      apiKey = parsed.apiKey || parsed.accessToken || parsed.token;
      baseUrl = parsed.url || parsed.baseUrl || 'https://api.deepseek.com/v1';
    } catch {
      apiKey = decrypted;
      baseUrl = 'https://api.deepseek.com/v1';
    }

    console.log("API Key:", apiKey ? apiKey.substring(0, 8) + "..." : "未找到");
    console.log("Base URL:", baseUrl);

    // 创建 openAiApi 凭证
    const newCredData = JSON.stringify({ apiKey, url: baseUrl });
    const encrypted = cipher.encrypt(newCredData);
    const newId = require('crypto').randomUUID();

    db.prepare(`
      INSERT INTO credentials_entity (id, name, type, data, createdAt, updatedAt)
      VALUES (?, ?, 'openAiApi', ?, datetime('now'), datetime('now'))
    `).run(newId, 'DeepSeek API (OpenAI Compat)', encrypted);

    console.log("=== 新凭证已创建 ===");
    console.log("ID:", newId);
    console.log("名称: DeepSeek API (OpenAI Compat)");
    console.log("类型: openAiApi");
  }
}

main().catch(e => { console.error(e); process.exit(1); });
