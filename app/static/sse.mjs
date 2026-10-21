export function parseFrame(frame) {
  let event = 'message';
  const data = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  return data.length ? {event, data: JSON.parse(data.join('\n'))} : null;
}

export async function* streamEvents(body) {
  if (!body) throw new Error('浏览器未提供流式响应正文');
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      let match;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const parsed = parseFrame(buffer.slice(0, match.index));
        buffer = buffer.slice(match.index + match[0].length);
        if (parsed) yield parsed;
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const parsed = parseFrame(buffer);
      if (parsed) yield parsed;
    }
  } finally { reader.releaseLock(); }
}
