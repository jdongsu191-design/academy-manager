export const config = { runtime: 'edge' };

export default async function handler(req) {
  if (req.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'API key not configured' }), {
      status: 500, headers: { 'Content-Type': 'application/json' }
    });
  }
  try {
    const body = await req.json();
    const message = body.messages && body.messages[0];
    const parts = [];
    if (Array.isArray(message && message.content)) {
      for (const part of message.content) {
        if (part.type === 'image') {
          parts.push({ inline_data: { mime_type: part.source.media_type, data: part.source.data } });
        } else if (part.type === 'text') {
          parts.push({ text: part.text });
        }
      }
    } else if (message && typeof message.content === 'string') {
      parts.push({ text: message.content });
    }
    if (parts.length === 0) {
      return new Response(JSON.stringify({ error: 'empty parts' }), {
        status: 400, headers: { 'Content-Type': 'application/json' }
      });
    }
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=' + apiKey;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts: parts }], generationConfig: { maxOutputTokens: body.max_tokens || 1000, temperature: 0.1 } })
    });
    const data = await response.json();
    if (data.error) {
      return new Response(JSON.stringify({ error: data.error.message }), {
        status: 400, headers: { 'Content-Type': 'application/json' }
      });
    }
    const text = (data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts && data.candidates[0].content.parts[0] && data.candidates[0].content.parts[0].text) || '';
    return new Response(JSON.stringify({ content: [{ type: 'text', text: text }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 500, headers: { 'Content-Type': 'application/json' }
    });
  }
}
