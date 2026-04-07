export const config = { runtime: 'edge' };
export default async function handler(req) {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return new Response(JSON.stringify({ error: 'no key' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  try {
    const body = await req.json();
    const msg = body.messages && body.messages[0];
    const parts = [];
    if (Array.isArray(msg && msg.content)) {
      for (const p of msg.content) {
        if (p.type === 'image') parts.push({ inline_data: { mime_type: p.source.media_type, data: p.source.data } });
        else if (p.type === 'text') parts.push({ text: p.text });
      }
    } else if (msg && typeof msg.content === 'string') {
      parts.push({ text: msg.content });
    }
    if (!parts.length) return new Response(JSON.stringify({ error: 'empty' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-001:generateContent?key=' + apiKey;
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contents: [{ parts }], generationConfig: { maxOutputTokens: 1000, temperature: 0.1 } }) });
    const d = await r.json();
    if (d.error) return new Response(JSON.stringify({ error: d.error.message }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    const text = d.candidates && d.candidates[0] && d.candidates[0].content && d.candidates[0].content.parts && d.candidates[0].content.parts[0] ? d.candidates[0].content.parts[0].text || '' : '';
    return new Response(JSON.stringify({ content: [{ type: 'text', text }] }), { status: 200, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }
}

