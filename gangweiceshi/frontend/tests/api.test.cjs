const assert = require('node:assert/strict');
const { test } = require('node:test');
const { getHealth, runUnifiedDaily } = require('../../../runtime/frontend-api-tests/api.js');

async function withResponse(response, check) {
  const original = global.fetch;
  global.fetch = async () => response;
  try { await check(); } finally { global.fetch = original; }
}

test('HTML gateway failures show the HTTP status rather than JSON parsing errors', async () => {
  await withResponse(new Response('<html>private gateway details</html>', { status: 502 }), async () => {
    await assert.rejects(getHealth(), (error) => error.message.includes('502') && !error.message.includes('private'));
  });
});

test('validation errors omit echoed request contents', async () => {
  const body = { detail: [{ loc: ['body', 'question'], msg: 'Question too long', input: 'private text' }] };
  await withResponse(new Response(JSON.stringify(body), { status: 422 }), async () => {
    await assert.rejects(getHealth(), (error) => error.message.includes('question: Question too long') && !error.message.includes('private text'));
  });
});

test('successful JSON stays unchanged', async () => {
  await withResponse(new Response('{"status":"healthy"}'), async () => {
    assert.deepEqual(await getHealth(), { status: 'healthy' });
  });
});

test('malformed successful responses are explicit errors', async () => {
  await withResponse(new Response('not JSON'), async () => {
    await assert.rejects(getHealth(), /无效数据/);
  });
});

for (const status of ['ok', 'partial', 'failed', 'unknown']) {
  test(`daily report preserves ${status} status and report body`, async () => {
    const payload = { status, report_title: '测试日报', report_text: '测试报告原文' };
    await withResponse(new Response(JSON.stringify(payload)), async () => {
      assert.deepEqual(await runUnifiedDaily(10, 10), payload);
    });
  });
}
