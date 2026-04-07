export default async function handler(req, res) {
  if (req.method !== 'POST') { res.status(405).send('Method Not Allowed'); return; }
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) { res.status(500).json({ error: 'no key' }); return; }
  try {
    const body = req.body;
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
    if (!parts.length) { res.status(400).json({ error: 'empty' }); return; }
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + apiKey;
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts }], generationConfig: { maxOutputTokens: 4096, temperature: 0.1 } })
    });
    const d = await r.json();
    if (d.error) { res.status(400).json({ error: d.error.message }); return; }
    const text = d.candidates && d.candidates[0] && d.candidates[0].content && d.candidates[0].content.parts && d.candidates[0].content.parts[0] ? d.candidates[0].content.parts[0].text || '' : '';
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json({ content: [{ type: 'text', text }] });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
