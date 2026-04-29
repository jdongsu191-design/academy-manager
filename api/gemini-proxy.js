export const config = { maxDuration: 60 };

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).send('Method Not Allowed');
    return;
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: 'Gemini API key not configured' });
    return;
  }

  try {
    const body = req.body;
    const model = body.model || 'gemini-2.5-flash';

    let contents = body.contents;

    // Supabase Storage URL 방식: imageUrls 배열이 있으면 fetch해서 inline_data로 변환
    if (Array.isArray(body.imageUrls) && body.imageUrls.length > 0) {
      const imageParts = await Promise.all(
        body.imageUrls.map(async (url) => {
          const r = await fetch(url);
          if (!r.ok) throw new Error('이미지 fetch 실패: ' + url);
          const buffer = await r.arrayBuffer();
          const base64 = Buffer.from(buffer).toString('base64');
          const mimeType = r.headers.get('content-type') || 'image/jpeg';
          return { inlineData: { mimeType, data: base64 } };
        })
      );
      // 텍스트 프롬프트는 body.prompt로 전달
      contents = [{
        parts: [...imageParts, { text: body.prompt || '' }]
      }];
    }

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents,
        generationConfig: body.generationConfig || {
          temperature: 0,
          maxOutputTokens: 8192,
          responseMimeType: 'application/json'
        }
      })
    });

    const data = await response.json();
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(response.status).json(data);

  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
