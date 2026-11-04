# Architecture — how the files connect

There is no single "mother file." The thing you **run** is
`scripts/run_batch.py`; the thing that **ties the logic together** is
`pgg/runner.py` (the conductor). Everything else is either an input you edit, a
library the conductor calls, or an output it produces.

## Diagram

```mermaid
flowchart TB
    subgraph INPUTS["YOU EDIT THESE (inputs)"]
        CFG["configs/*.yaml<br/>experiment knobs"]
        PDEF["personas/defs/*.md<br/>5 personalities, 1 file per person"]
        PROMPTS["pgg/prompts/*.md<br/>text sent to the AI"]
    end

    RUN["scripts/run_batch.py<br/><b>THE COMMAND YOU RUN</b>"]

    subgraph BRAIN["pgg/ — the logic"]
        CONFIG["config.py<br/>reads &amp; validates the YAML"]
        RUNNER["runner.py<br/><b>the conductor</b><br/>drives the game, calls agents, logs"]
        ENGINE["engine.py<br/>pure game rules<br/>(pot, split, punish)"]
        subgraph AGENTS["agents/"]
            MOCK["mock_agents.py<br/>fake players (offline)"]
            LLM["llm_agent.py<br/>real AI players"]
        end
        CLIENT["llm/client.py<br/>talks to the models"]
        PLOADER["prompts/persona_loader.py<br/>+ builder.py"]
        LOG["logging_.py<br/>writes files"]
        METRICS["metrics.py<br/>computes stats"]
    end

    PROXY(["CLIProxyAPI + Kiro account<br/>(external — not wired yet)"])

    subgraph OUTPUTS["CREATED WHEN YOU RUN (outputs)"]
        OUT["runs/&lt;run_id&gt;/&lt;game_id&gt;/<br/>config.json · rounds.jsonl<br/>calls.jsonl · summary.json"]
    end

    RUN -->|"1. load config"| CONFIG
    CFG --> CONFIG
    RUN -->|"2. start games"| RUNNER

    CONFIG --> RUNNER
    RUNNER -->|"applies the rules"| ENGINE
    RUNNER -->|"asks for decisions"| AGENTS
    PDEF --> PLOADER
    PLOADER --> RUNNER
    PROMPTS --> LLM
    LLM --> CLIENT
    CLIENT -.->|"HTTP (base_url)"| PROXY
    MOCK -. "offline alternative" .-> RUNNER

    RUNNER -->|"writes each round"| LOG
    LOG --> OUT
    RUNNER -->|"at the end"| METRICS
    METRICS --> OUT

    classDef input fill:#e6f3ff,stroke:#2b6cb0,color:#1a365d;
    classDef output fill:#e6ffed,stroke:#2f855a,color:#22543d;
    classDef run fill:#fff5e6,stroke:#dd6b20,color:#7b341e;
    classDef ext fill:#f0e6ff,stroke:#6b46c1,color:#44337a;
    class CFG,PDEF,PROMPTS input;
    class OUT output;
    class RUN run;
    class PROXY ext;
```

## How to read it

1. You run `scripts/run_batch.py` — the only command.
2. It loads your chosen `configs/*.yaml` via `config.py`.
3. It hands control to `runner.py`, the conductor.
4. The conductor loops through each round: it asks `engine.py` to apply the
   rules, asks the agents (mock or LLM) for decisions, and — for LLM agents —
   sends prompts through `llm/client.py` to the models (CLIProxyAPI plugs in
   here).
5. Each round is written by `logging_.py`; at the end `metrics.py` computes the
   stats.
6. You get a `runs/<run_id>/<game_id>/` folder of data.

The three blue boxes are the only things you normally edit. The purple box
(CLIProxyAPI) is the one piece not yet connected.
