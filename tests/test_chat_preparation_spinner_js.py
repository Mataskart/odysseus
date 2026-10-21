import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
CHAT = (REPO / "static/js/chat.js").read_text(encoding="utf-8")
PREPARATION_HANDLER = CHAT.split("if (json.type === 'agent_prep') {", 1)[1].split(
    "if (json.type === 'tool_approval_resolved') {", 1
)[0]
WAIT_TIMERS = CHAT.split("const scheduleFirstTokenWaitMessages =", 1)[1].split(
    "const clearProcessingProbe =", 1
)[0]


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
@pytest.mark.parametrize("background,initial_spinner", [(False, True), (False, False), (True, True)])
def test_tool_preparation_keeps_one_visible_status(background, initial_spinner):
    script = """
      let message = 'Preparing conversation context';
      let thinkingCards = 0;
      let createdCards = 0;
      let accumulated = '';
      let abortCtrl = null;
      let firstTokenWaitTimers = [];
      const timers = new Map();
      let nextTimer = 0;
      const setTimeout = (callback, delay) => {
        const id = ++nextTimer;
        timers.set(id, {callback, delay});
        return id;
      };
      const clearTimeout = id => timers.delete(id);
      const clearFirstTokenWaitTimers = () => {
        firstTokenWaitTimers.forEach(clearTimeout);
        firstTokenWaitTimers = [];
      };
      const _cancelThinkingTimer = () => {};
      const _removeThinkingSpinner = () => { thinkingCards = 0; };
      const _showThinkingSpinner = label => {
        thinkingCards = 1;
        createdCards++;
        message = label;
      };
    """
    script += f"""
      const _isBg = {json.dumps(background)};
      const spinner = {"{element: {}, updateMessage: label => { message = label; }}" if initial_spinner else "null"};
      const scheduleFirstTokenWaitMessages = {WAIT_TIMERS}
      for (const json of [{{type: 'agent_prep'}}, {{type: 'agent_prep'}}]) {{
        if (json.type === 'agent_prep') {{{PREPARATION_HANDLER}
      }}
      const afterPreparation = message;
      for (const timer of timers.values()) {{
        if (timer.delay === 12000) timer.callback();
      }}
      console.log(JSON.stringify({{
        afterPreparation, message, thinkingCards, createdCards,
        visibleCards: (spinner ? 1 : 0) + thinkingCards,
        timerCount: timers.size,
      }}));
    """
    result = subprocess.run(
        ["node", "--input-type=module"], input=script, capture_output=True,
        text=True, cwd=REPO, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["visibleCards"] == 1
    if background:
        assert output["message"] == "Preparing conversation context"
        assert output["createdCards"] == 0
        assert output["timerCount"] == 0
    else:
        assert output["afterPreparation"] == "Tool selection complete · waiting for model"
        assert output["timerCount"] == 4
        if initial_spinner:
            assert output["createdCards"] == 0
            assert output["message"] == "Request prepared · waiting for model startup · 12s"
        else:
            assert output["thinkingCards"] == 1
