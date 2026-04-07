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
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + apiKey;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
