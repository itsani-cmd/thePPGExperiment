# Setup: install everything on a new computer

This guide takes a computer from nothing to running real games. It is written so
that a person or an AI coding agent can follow it step by step.

```
run_batch.py  --HTTP-->  CLIProxyAPI (127.0.0.1:8317)  -->  your AI account (ChatGPT, Claude, ...)
```

The harness (this repo) sends requests to an OpenAI-compatible API.
[CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) is a separate
program that runs on the same computer, logs in to the user's AI account, and
provides that API. It is not part of this repo and is not installed inside it.

## Instructions for AI agents

- Do the steps in order. After each step, run its **Check** and compare with
  **Expected**. Do not continue if the check fails; see Troubleshooting.
- Steps marked **HUMAN** need the person at the keyboard (a browser login).
  Stop, tell them the exact command, and wait until they say it is done.
- The proxy (step 6) runs until stopped. Start it as a background process, not
  as a command that waits for it to finish.
- Never print, log, or commit the client key in `~/cliproxyapi/pgg_api_key.txt`
  or anything in `~/.cli-proxy-api/`. Read the key into an environment variable.
- Do not commit to git unless the person asks.
- Do not run large batches without asking. A full game is about 150 model calls
  and uses the person's plan limits.

## What you need

| need | details |
| --- | --- |
| Python | 3.9 or newer (`python3 --version`) |
| git | to clone the repo |
| curl, tar | preinstalled on macOS and most Linux; on Windows see the Windows section |
| AI account | one that CLIProxyAPI can log in to: ChatGPT (free works), Claude (Claude Code, probably a paid plan), or a Google account for Gemini |

A Kiro account alone will not work: CLIProxyAPI has no Kiro login.

## Step 1: Get the project

```bash
git clone https://github.com/itsani-cmd/thePPGExperiment.git
cd thePPGExperiment
python3 -m venv .venv
source .venv/bin/activate
pip install pydantic pyyaml openai pytest
```

**Check:** `python -m pytest -q`
**Expected:** a line of dots ending in `[100%]` and no `FAILED` lines.

## Step 2: Check the game runs offline

```bash
python scripts/run_batch.py --config configs/smoke_chatgpt.yaml --agents mock --mock-type random --run-id offline_check --live
```

**Expected:** two rounds printed, then `Completed 1 game(s). Logs in runs/offline_check`.
This uses no AI account. Delete it afterwards with `rm -rf runs/offline_check`.

## Step 3: Download CLIProxyAPI

This downloads the latest release for this computer into `~/cliproxyapi`
(outside the project) and checks it against the published checksum. Works on
macOS and Linux.

```bash
mkdir -p ~/cliproxyapi && cd ~/cliproxyapi
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in arm64|aarch64) ARCH=aarch64;; x86_64|amd64) ARCH=amd64;; esac
TAG=$(curl -fsSL https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/latest \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])")
ASSET="CLIProxyAPI_${TAG#v}_${OS}_${ARCH}.tar.gz"
BASE="https://github.com/router-for-me/CLIProxyAPI/releases/download/$TAG"
curl -fsSLO "$BASE/$ASSET" && curl -fsSLO "$BASE/checksums.txt"
grep " $ASSET\$" checksums.txt | (shasum -a 256 -c - 2>/dev/null || sha256sum -c -)
tar -xzf "$ASSET" && rm "$ASSET"
./cli-proxy-api --help | head -1
```

**Expected:** a line ending in `: OK` (checksum matches), then
`CLIProxyAPI Version: ...`.
If the checksum line does not say `OK`, delete the download and stop.

Tested with v8.0.58. If a newer release breaks something, set `TAG=v8.0.58`
instead of looking up the latest.

## Step 4: Create the proxy config and client key

The key is a password the harness uses to talk to the proxy. It is random,
stays on this computer, and is not an AI-provider key.

```bash
cd ~/cliproxyapi
KEY="pgg-$(openssl rand -hex 24)"
umask 077
echo "$KEY" > pgg_api_key.txt
cat > config.yaml <<EOF
config-version: 8
server:
  host: "127.0.0.1"
  port: 8317
access:
  api-keys:
    - "$KEY"
oauth:
  auth-dir: "~/.cli-proxy-api"
EOF
unset KEY
```

`host: "127.0.0.1"` means only this computer can reach the proxy.

**Check:** `ls -l ~/cliproxyapi/config.yaml ~/cliproxyapi/pgg_api_key.txt`
**Expected:** both files exist and start with `-rw-------` (owner only).

## Step 5: Log in to an AI account (HUMAN)

Run **one** of these in a terminal. It opens a browser; the person signs in.

| account | command |
| --- | --- |
| ChatGPT | `cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml --codex-login` |
| ChatGPT, no browser on this machine | `cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml --codex-device-login` |
| Claude | `cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml --claude-login` |
| Google (Gemini) | `cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml --antigravity-login` |

Only the ChatGPT login has been tested with this project.

**Check:** `ls ~/.cli-proxy-api/`
**Expected:** a `.json` file named after the provider and account, such as
`codex-...-free.json`. A name ending in `-free` means a free plan with low
usage limits.

## Step 6: Start the proxy

Run this in its own terminal and leave it open. Agents: start it as a
background process.

```bash
cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml
```

The proxy must be running whenever games run. After a restart or a closed
terminal, run this command again.

## Step 7: Connect the project to the proxy

In the project folder, in every new terminal:

```bash
source .venv/bin/activate
export PGG_BASE_URL=http://127.0.0.1:8317/v1
export PGG_API_KEY="$(cat ~/cliproxyapi/pgg_api_key.txt)"
```

List the models the proxy serves:

```bash
curl -s -H "Authorization: Bearer $PGG_API_KEY" $PGG_BASE_URL/models \
  | python3 -c "import sys,json;print('\n'.join(m['id'] for m in json.load(sys.stdin)['data']))"
```

**Expected:** a list of model names. Skip names containing `image` (image
models) and `review`.

If the list does not include `gpt-6-luna` (for example on a Claude account),
open `configs/smoke_chatgpt.yaml` and `configs/local_chatgpt.yaml` and change
`model: gpt-6-luna` to a name from the list.

## Step 8: Run a test game

```bash
python scripts/run_batch.py --config configs/smoke_chatgpt.yaml --agents llm --run-id setup_check --live
```

**Expected:** two rounds printed with real messages from the agents, then
`Completed 1 game(s)`. Takes about a minute.

**Check** that no call fell back to a default:

```bash
python - runs/setup_check/game_0000 <<'PY'
import json, sys, os
d = sys.argv[1]
calls = [json.loads(l) for l in open(os.path.join(d, "calls.jsonl")) if l.strip()]
rounds = [json.loads(l) for l in open(os.path.join(d, "rounds.jsonl")) if l.strip()]
fallbacks = sum(
    sum(r["contribution_fallbacks"].values())
    + sum(p["fallback_used"] for p in r["punishments"])
    + sum(m["fallback_used"] for m in r["messages"])
    for r in rounds
)
done = os.path.exists(os.path.join(d, "summary.json"))
print(f"calls={len(calls)} errors={sum(1 for c in calls if c['error'])} fallbacks={fallbacks} finished={done}")
print("RESULT:", "PASS" if calls and fallbacks == 0 and done else "FAIL")
PY
```

**Expected:** `RESULT: PASS`. A few `errors` with `fallbacks=0` is fine (a retry
worked). If it says `FAIL`, look at the errors:

```bash
python -c "import json;[print(c['phase'],c['error']) for c in map(json.loads,open('runs/setup_check/game_0000/calls.jsonl')) if c['error']][:5]"
```

Setup is complete when this passes.

## Running everything

Each new terminal session:

1. Start the proxy (step 6) if it is not running.
2. In the project folder, run the three lines in step 7.
3. Run games:

```bash
# see how many calls a run will make
python scripts/run_batch.py --config configs/local_chatgpt.yaml --dry-run

# one full game with the five personas, printed live
python scripts/run_batch.py --config configs/local_chatgpt.yaml --agents llm --live

# a variation, 3 games
python scripts/run_batch.py --config configs/v2_comm_off.yaml --agents llm --games 3 --live

# replay the most recent game
python scripts/show_game.py
```

Before running the `v1_*`, `v2_*`, `v3_*`, `baseline` or `personas_five`
configs with real models, change their `model: gpt-4o-mini` to a model from
step 7. The full list of configs and settings is in [`README.md`](README.md).

If a run stops partway, continue it with
`--resume <run_id>` (same config); finished games are skipped.

## Windows

The project itself works on Windows. The commands differ:

| macOS / Linux | Windows (PowerShell) |
| --- | --- |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| `export PGG_BASE_URL=...` | `$env:PGG_BASE_URL = "http://127.0.0.1:8317/v1"` |
| `export PGG_API_KEY="$(cat ~/cliproxyapi/pgg_api_key.txt)"` | `$env:PGG_API_KEY = Get-Content $HOME\cliproxyapi\pgg_api_key.txt` |
| `./cli-proxy-api` | `.\cli-proxy-api.exe` |

For step 3, download `CLIProxyAPI_<version>_windows_amd64.zip` (or
`windows_aarch64`) and `checksums.txt` from the
[releases page](https://github.com/router-for-me/CLIProxyAPI/releases), check it
with `Get-FileHash <file> -Algorithm SHA256`, and unzip it into
`%USERPROFILE%\cliproxyapi`. For step 4, write the same `config.yaml` by hand
with any long random string as the key, and save that string in
`pgg_api_key.txt`. The Windows steps have not been tested.

## Troubleshooting

| symptom | cause and fix |
| --- | --- |
| `Failed to connect to ... port 8317` / `Connection refused` | proxy not running. Do step 6. |
| `401` or `Unauthorized` | `PGG_API_KEY` not set in this terminal, or it doesn't match `config.yaml`. Redo step 7. |
| `configured models not served by the endpoint: ...` | the config's `model:` is not in the proxy's list. Change it (step 7). |
| `/models` returns an empty list | no account logged in. Do step 5, then restart the proxy. |
| many `fallback_used` / errors mentioning rate limit, quota or 429 | plan usage limit reached. Wait for it to reset or use a paid plan. |
| errors mentioning `response_format` or JSON mode | set `json_mode: false` under the model in the config. |
| `pip install -e .` fails with a Python version error | use `pip install pydantic pyyaml openai pytest` instead (step 1). |
| run finishes instantly with the same result as before | that `--run-id` already has a finished game. Use a new run id. |
| `ModuleNotFoundError: pydantic` (or yaml, openai) | the virtual environment is not active. Run `source .venv/bin/activate`. |

## Security notes

- The proxy listens only on `127.0.0.1`; other computers cannot use it.
- `~/cliproxyapi/pgg_api_key.txt` and `~/.cli-proxy-api/` hold credentials.
  They are outside the repo; keep them out of git and out of chat.
- The harness never writes the key into `runs/` logs.
- To log out, stop the proxy and delete the account file in `~/.cli-proxy-api/`.
