import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("http_ok,result,expected", [
    (True, {"recorded": True, "status": "saved"}, "✓"),
    (True, {"recorded": False, "status": "logging_disabled"}, "!"),
    (True, {"recorded": False, "status": "write_failed"}, "!"),
    (False, {"detail": "Reply not found"}, "!"),
])
def test_flag_button_uses_server_recording_result(http_ok, result, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for UI behavior checks")
    source = Path("static/js/chatRenderer.js").read_text()
    start = source.index("      const btn = e.currentTarget;", source.index("{ id: 'flag'"))
    end = source.index("    }},", start)
    body = source[start:end]
    script = '''
const btn = {};
const e = {currentTarget: btn};
const window = {sessionModule: {getCurrentSessionId: () => 'session'}};
const msgElement = {dataset: {dbId: 'reply'}};
let posted;
const fetch = async (url, options) => {
  posted = JSON.parse(options.body);
  return {ok: HTTP_OK, json: async () => (RESULT)};
};
(function () {
BODY
})();
setImmediate(() => process.stdout.write(JSON.stringify({btn, posted})));
'''.replace("HTTP_OK", json.dumps(http_ok)).replace("RESULT", json.dumps(result)).replace("BODY", body)
    response = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
    actual = json.loads(response.stdout)
    assert actual["btn"]["textContent"] == expected
    assert actual["posted"] == {"session_id": "session", "message_id": "reply"}
