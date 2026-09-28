"""IBM Bob client: runs Bob Shell headless (`bob run --format json`) as the reasoning engine.

Bob has no plain HTTP API; the documented way to automate it is Bob Shell in non-interactive
mode, authenticated with the BOB_API_KEY environment variable
(https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive).

Safety: `bob run` pre-approves tools, and uploaded posts are untrusted text. Every call
therefore runs in "ask" mode with the command/edit/browser/MCP/subagent tool groups disabled,
inside an empty temporary workspace, with a turn limit. The prompt goes through stdin, never
through a shell command line.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading

from threatlens.paths import PKG_DIR, SAMPLE_DATA

log = logging.getLogger(__name__)

CACHE_PATH = SAMPLE_DATA / "llm_cache.json"
TIMEOUT_S = int(os.getenv("BOB_TIMEOUT_S", "240"))
_lock = threading.Lock()
_disabled: str | None = None  # set after an auth/installation failure so the app never waits twice


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(PKG_DIR.parent / ".env")
    except Exception:
        pass


def bob_executable() -> str | None:
    return shutil.which("bob") or shutil.which("bob.cmd")


def status() -> dict:
    """{'ready': bool, 'detail': str} for the UI."""
    _load_env()
    if _disabled:
        return {"ready": False, "detail": f"unavailable this session: {_disabled}"}
    if not os.getenv("BOB_API_KEY"):
        return {"ready": False, "detail": "BOB_API_KEY not set in src/.env"}
    if not bob_executable():
        return {"ready": False, "detail": "Bob Shell not installed (see docs/setup-guide.md)"}
    return {"ready": True, "detail": "IBM Bob Shell connected"}


def reset() -> None:
    global _disabled
    _disabled = None


def cache_key(task: str, payload) -> str:
    return hashlib.sha256(json.dumps([task, payload], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def cache_get(key: str):
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")).get(key)
    except Exception:
        return None


def cache_put(key: str, value) -> None:
    with _lock:
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
        cache[key] = value
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def run(prompt: str, max_turns: int = 3) -> tuple[str, float]:
    """Send one prompt to Bob. Returns (reply text, bobcoin cost). Raises RuntimeError on failure."""
    global _disabled
    st = status()
    if not st["ready"]:
        raise RuntimeError(st["detail"])
    cmd = [bob_executable(), "run", "--format", "json", "--mode", "ask", "--disable-mcp", "--disable-subagents",
           "--disable-tool-groups", "command,edit,browser,mcp,subagent", "--max-turns", str(max_turns),
           "--accept-license", "--trust", "--log-level", "error"]
    if os.getenv("BOB_TEAM_ID"):
        cmd += ["--team-id", os.environ["BOB_TEAM_ID"]]
    workspace = tempfile.mkdtemp(prefix="threatlens_bob_")
    try:
        proc = subprocess.run(cmd + ["-w", workspace], input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TIMEOUT_S, cwd=workspace,
                              env={**os.environ, "BOB_LOG_LEVEL": "error"})
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Bob did not answer within {TIMEOUT_S} s")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    result = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"type"' in line:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "result":
                result = obj
    if not result or result.get("status") != "success":
        detail = (result or {}).get("error") or (proc.stderr or proc.stdout or "no output")[-300:]
        if re.search(r"auth|api key|401|403|unauthori|license", str(detail), re.I):
            _disabled = f"authentication failed: {str(detail)[:120]}"
        raise RuntimeError(f"Bob call failed: {str(detail)[:300]}")
    return result.get("last_message") or "", float(result.get("stats", {}).get("session_costs") or 0)


def extract_json(text: str):
    """First JSON object or array in a reply (tolerates ```json fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in Bob reply")
    return json.JSONDecoder().raw_decode(text[min(starts):])[0]
