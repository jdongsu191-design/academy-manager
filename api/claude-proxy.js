export const config = { runtime: 'edge' };

export default async function handler(req) {
  if (req.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'API key not configured' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const body = await req.json();
    const message = body.messages?.[0];
    const parts = [];

    if (Array.isArray(message?.content)) {
      for (const part of message.content) {
        if (part.type === 'image') {
          parts.push({ inline_data: { mime_type: part.source.media_type, data: part.source.data } });
        } else if (part.type === 'text') {
          parts.push({ text: part.text });
        }
      }
    } else if (typeof message?.content === 'string') {
      parts.push({ text: message.content });
    }

    // parts가 비어있으면 오류 반환 (디버그)
    if (parts.length === 0) {
      return new Response(JSON.stringify({ error: 'empty parts', debug: { message } }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' + apiKey;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts }], generationConfig: { maxOutputTokens: body.max_tokens || 1000, temperature: 0.1 } })
    });

    const data = await response.json();
    // Gemini 오류 시 그대로 반환 (디버그)
    if (data.error) {
      return new Response(JSON.stringify({ error: data.error }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';

    return new Response(JSON.stringify({ content: [{ type: 'text', text }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
