import json
import threading
from urllib.request import Request, urlopen
from werkzeug.serving import make_server
from tests.test_lesson5_flow import FlowFixture
from tests.test_lesson5_sse import decode_events


class WireTests(FlowFixture):
    def test_http_flush_before_upstream_finishes(self):
        release = threading.Event()
        finished = threading.Event()
        def provider(messages):
            yield "先检查这一步所使用的依据是否与题目条件一致。"
            if not release.wait(5):
                raise RuntimeError("test release timed out")
            yield "下一步说明你还不能确认的地方。"
            finished.set()
        self.app.config["CHAT_STREAM_FACTORY"] = provider
        # This agent has no materials, so the wire test does not need embeddings.
        self.client.patch(f"/api/agents/{self.agent_a}", json={"material_ids": []}, headers=self.teacher)
        server = make_server("127.0.0.1", 0, self.app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f"http://127.0.0.1:{server.server_port}/api/conversations/{self.cid}/messages",
                              method="POST", headers={**self.student, "Content-Type": "application/json"},
                              data=json.dumps({"question": "方程这一步怎么检查"}).encode())
            with urlopen(request, timeout=8) as response:
                first = b""
                while not first.endswith(b"\n\n"):
                    first += response.readline()
                self.assertEqual(decode_events(first.decode())[0][0], "meta")
                delta = b""
                while not delta.endswith(b"\n\n"):
                    delta += response.readline()
                self.assertEqual(decode_events(delta.decode())[0][0], "delta")
                self.assertFalse(finished.is_set())
                release.set()
                events = decode_events((first + delta + response.read()).decode())
                self.assertEqual(events[-1][0], "done")
                self.assertGreater(sum(name == "delta" for name, _ in events), 1)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
