import assert from 'node:assert/strict';
import {streamEvents} from '../app/static/sse.mjs';
const wire = 'event: meta\r\ndata: {"status":"ok","skill":"数学解题引导","citations":[]}\r\n\r\nevent: delta\ndata: {"text":"第一段"}\n\nevent: delta\ndata: {"text":"第二段"}\n\nevent: done\ndata: {"message_id":8}\n\n';
const bytes = new TextEncoder().encode(wire);
for (const size of [1, 2, 7, 31]) {
  const stream = new ReadableStream({start(controller) {
    for (let index=0; index<bytes.length; index+=size) controller.enqueue(bytes.slice(index,index+size));
    controller.close();
  }});
  const events = [];
  for await (const event of streamEvents(stream)) events.push(event);
  assert.deepEqual(events.map(item=>item.event), ['meta','delta','delta','done']);
  assert.equal(events[0].data.skill, '数学解题引导');
  assert.equal(events.filter(item=>item.event==='delta').map(item=>item.data.text).join(''), '第一段第二段');
  assert.equal(events[3].data.message_id,8);
}
console.log('PASS: UTF-8 byte boundaries, CRLF/LF frames, incremental deltas and done');
