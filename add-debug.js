const fs = require('fs');
const file = '/usr/local/lib/node_modules/n8n/node_modules/.pnpm/@n8n+n8n-nodes-langchain@file+packages+@n8n+nodes-langchain_e536a10f8c135473d15b0e9f4526bc3b/node_modules/@n8n/n8n-nodes-langchain/dist/nodes/llms/LMChatOpenAi/LmChatOpenAi.node.js';
let content = fs.readFileSync(file, 'utf8');

const debugLine = [
  "        console.log('[DEBUG LmChatOpenAi] modelName:', modelName);",
  "        console.log('[DEBUG LmChatOpenAi] configuration.baseURL:', configuration.baseURL);",
  "        console.log('[DEBUG LmChatOpenAi] options.baseURL:', options.baseURL);",
  "        console.log('[DEBUG LmChatOpenAi] credentials.url:', credentials.url);",
  "        console.log('[DEBUG LmChatOpenAi] credentials.apiKey first 10:', credentials.apiKey?.substring(0, 10));",
].join('\n');

content = content.replace(
  'const model = new openai_1.ChatOpenAI(fields);',
  debugLine + '\n        const model = new openai_1.ChatOpenAI(fields);'
);

fs.writeFileSync(file, content);
console.log('Debug logging added to LmChatOpenAi.node.js');
