# Meme Radar Agent

`bn_meme_radar` is a read-only multi-chain meme radar with optional Binance MCP access.

It is structured to fit both contest activities:

- Track A: an Agent OS-style utility that discovers, reasons about, and scores meme tokens across multiple chains.
- Track B: a Binance MCP client wrapper that can probe tools, inspect market data, and call MCP tools directly.

## What it does

- Scans BSC, Solana, and optional Robinhood Chain token feeds.
- Scores tokens using liquidity, volume, price change, buy/sell flow, and public-info signals.
- Prints a ranked hotspot list with simple risk flags.
- Includes an `--agent` mode that renders an observe/reason/risk/next-action cycle for demos.
- Connects to the official Binance MCP endpoint and can list or call exposed tools.
- Keeps the default mode read-only: no private keys, no signing, no automatic order placement.

## Quick Start

```powershell
pip install -r requirements.txt
python meme_radar.py --chains bsc,solana --limit 10
python meme_radar.py --json
```

## Track A Demo

Use the agent output as the Agent OS demo:

```powershell
python meme_radar.py --agent --chains bsc,solana,robinhood --limit 20
python meme_radar.py --json > hotspots.json
```

This gives you a concrete GitHub project plus a visible agent-style workflow.

## Recording Commands

Use these commands during a demo or verification run:

```powershell
python meme_radar.py --agent --chains bsc,solana --limit 5
python meme_radar.py --chains bsc,solana --limit 10
codex mcp list
codex mcp get binance
codex mcp login binance
python meme_radar.py --mcp-probe
python meme_radar.py --mcp-list-tools
python meme_radar.py --mcp-account
```

If you need to re-authorize Binance MCP, run:

```powershell
codex mcp logout binance
codex mcp login binance
```

## Track B Demo

Official Binance MCP endpoint:

`https://agent.binance.com/mcp/agentic`

Useful verification commands:

```powershell
python meme_radar.py --mcp-probe
python meme_radar.py --mcp-list-tools
python meme_radar.py --mcp-discover ticker price balance trade order buy sell
python meme_radar.py --mcp-symbol-detail BTCUSDT
python meme_radar.py --mcp-kline BTCUSDT
python meme_radar.py --mcp-market BTCUSDT
python meme_radar.py --mcp-discover-price
python meme_radar.py --mcp-account
python meme_radar.py --mcp-call <tool_name> --mcp-args "{}"
```

If your environment already sets `BINANCE_MCP_URL`, you can omit `--mcp-url`.

## Repo Link

GitHub: [https://github.com/alishaoxiong/bn_meme_radar](https://github.com/alishaoxiong/bn_meme_radar)

## Submission Note

If you want a short message to post with the repo, use:

> I am submitting `bn_meme_radar` for both contest activities: Track A for the multi-chain meme radar agent, and Track B for Binance MCP integration and tool calls.
