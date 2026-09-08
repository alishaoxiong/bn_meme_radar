#!/usr/bin/env python3

"""Read-only multi-chain meme hotspot radar with optional Binance MCP access."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))

from binance_mcp import (  # noqa: E402
    BinanceMCPClient,
    DEFAULT_BINANCE_MCP_URL,
    render_tool_result,
    summarize_tool_call,
)

DEX_URL = "https://api.dexscreener.com"
SUPPORTED = {"bsc", "solana", "robinhood"}


@dataclass
class HotToken:
    chain: str
    symbol: str
    name: str
    address: str
    pair_url: str
    price_usd: Optional[float]
    liquidity_usd: float
    volume_24h_usd: float
    buys_24h: int
    sells_24h: int
    price_change_24h_pct: float
    boosts: float
    score: float
    risk_flags: list[str]
    source: str
    observed_at: int


@dataclass
class AgentRecommendation:
    primary_chain: str
    primary_symbol: str
    thesis: str
    why_now: list[str]
    watchouts: list[str]
    next_actions: list[str]


def get_json(url: str, timeout: int = 15) -> Any:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "meme-radar/0.1"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def risk_flags(pair: dict[str, Any], liquidity: float, volume: float) -> list[str]:
    flags: list[str] = []
    tx = pair.get("txns") or {}
    h24 = tx.get("h24") or {}
    buys, sells = int(h24.get("buys") or 0), int(h24.get("sells") or 0)

    if liquidity < 25_000:
        flags.append("low-liquidity")
    if buys + sells and sells > buys * 2:
        flags.append("sell-pressure-high")
    if volume > 0 and liquidity > 0 and volume / liquidity > 20:
        flags.append("volume/liquidity-anomaly")

    info = pair.get("info") or {}
    if not info.get("websites") and not info.get("socials"):
        flags.append("missing-public-info")

    return flags


def score_pair(pair: dict[str, Any], boosts: float = 0) -> HotToken:
    chain = str(pair.get("chainId") or "unknown").lower()
    base = pair.get("baseToken") or {}
    liquidity = num((pair.get("liquidity") or {}).get("usd"))
    volume = num((pair.get("volume") or {}).get("h24"))
    change = num((pair.get("priceChange") or {}).get("h24"))
    tx = (pair.get("txns") or {}).get("h24") or {}
    buys, sells = int(tx.get("buys") or 0), int(tx.get("sells") or 0)

    # Transparent heuristic, intentionally not a trading signal.
    activity = min(35.0, (volume / max(liquidity, 1.0)) * 5.0)
    momentum = max(-15.0, min(30.0, change * 0.6))
    flow = max(-10.0, min(15.0, (buys - sells) / max(buys + sells, 1) * 15))
    liquidity_score = min(20.0, liquidity / 100_000 * 20)
    boost_score = min(10.0, boosts)
    total = round(max(0.0, min(100.0, 25 + activity + momentum + flow + liquidity_score + boost_score)), 2)

    return HotToken(
        chain=chain,
        symbol=str(base.get("symbol") or "?")[:32],
        name=str(base.get("name") or "Unknown")[:80],
        address=str(base.get("address") or ""),
        pair_url=str(pair.get("url") or ""),
        price_usd=num(pair.get("priceUsd")) or None,
        liquidity_usd=round(liquidity, 2),
        volume_24h_usd=round(volume, 2),
        buys_24h=buys,
        sells_24h=sells,
        price_change_24h_pct=round(change, 2),
        boosts=round(boosts, 2),
        score=total,
        risk_flags=risk_flags(pair, liquidity, volume),
        source="dexscreener",
        observed_at=int(time.time()),
    )


def fetch_dexscreener(chains: set[str]) -> list[HotToken]:
    profiles = get_json(f"{DEX_URL}/token-profiles/latest/v1")
    boosts = get_json(f"{DEX_URL}/token-boosts/top/v1")
    boost_map = {str(x.get("tokenAddress")): num(x.get("totalAmount")) for x in (boosts or [])}
    out: list[HotToken] = []
    seen: set[str] = set()

    for item in profiles or []:
        chain = str(item.get("chainId") or "").lower()
        if chain not in chains or chain not in SUPPORTED:
            continue

        address = str(item.get("tokenAddress") or "")
        if not address or address in seen:
            continue

        seen.add(address)

        try:
            data = get_json(f"{DEX_URL}/latest/dex/tokens/{address}")
            pairs = [p for p in (data.get("pairs") or []) if str(p.get("chainId")).lower() == chain]
            if pairs:
                best = max(pairs, key=lambda p: num((p.get("volume") or {}).get("h24")))
                out.append(score_pair(best, boost_map.get(address, 0)))
        except Exception:
            continue

    return out


def fetch_robinhood() -> list[HotToken]:
    """Optional adapter; configure MEME_RADAR_RH_URL to a read-only JSON feed."""

    url = os.getenv("MEME_RADAR_RH_URL")
    if not url:
        return []

    data = get_json(url)
    return [score_pair({**p, "chainId": "robinhood"}, num(p.get("boosts"))) for p in (data.get("pairs") or [])]


def fetch(chains: set[str]) -> list[HotToken]:
    result = fetch_dexscreener(chains) if chains else []
    if "robinhood" in chains:
        result.extend(fetch_robinhood())
    return sorted(result, key=lambda x: x.score, reverse=True)


def row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def build_recommendation(rows: list[Any]) -> AgentRecommendation:
    if not rows:
        return AgentRecommendation(
            primary_chain="unknown",
            primary_symbol="none",
            thesis="No ranked tokens were available from the current data source.",
            why_now=["The feed returned no usable pairs."],
            watchouts=["Try again later or switch to a different chain set."],
            next_actions=["Re-run the scan after the source refreshes."],
        )

    top = rows[0]
    backup = rows[1] if len(rows) > 1 else None
    top_symbol = str(row_value(top, "symbol", "unknown"))
    top_chain = str(row_value(top, "chain", "unknown"))
    top_score = float(row_value(top, "score", 0.0))
    top_change = float(row_value(top, "price_change_24h_pct", 0.0))
    thesis = (
        f"{top_symbol} on {top_chain} is the current watchlist leader because it combines "
        f"score {top_score:.2f} with {top_change:.2f}% 24h change."
    )
    if backup:
        thesis += f" {row_value(backup, 'symbol', 'backup')} is the backup candidate if the leader loses momentum."

    why_now = [
        f"Lead token: {top_symbol} on {top_chain} with score {top_score:.2f}.",
        f"24h move: {top_change:.2f}%, volume ${float(row_value(top, 'volume_24h_usd', 0.0)):,.0f}.",
        f"Liquidity: ${float(row_value(top, 'liquidity_usd', 0.0)):,.0f}, boosts: {float(row_value(top, 'boosts', 0.0)):.2f}.",
    ]
    if backup:
        why_now.append(
            f"Secondary watch: {row_value(backup, 'symbol', 'backup')} on {row_value(backup, 'chain', 'unknown')} "
            f"at score {float(row_value(backup, 'score', 0.0)):.2f}."
        )

    watchouts = list(row_value(top, "risk_flags", []) or ["No immediate red flags from the current heuristic."])
    watchouts.append("This is a read-only radar and not a trading signal.")

    next_actions = [
        f"Watch {top_symbol} for confirmation on the next refresh.",
        "Open the pair page before any human decision.",
        "If Binance MCP is connected later, enrich this watchlist with live account context.",
    ]

    return AgentRecommendation(
        primary_chain=top_chain,
        primary_symbol=top_symbol,
        thesis=thesis,
        why_now=why_now,
        watchouts=watchouts,
        next_actions=next_actions,
    )


def render_agent_report(rows: list[HotToken]) -> None:
    recommendation = build_recommendation(rows)
    print("=== Observe ===")
    print(f"Scanned {len(rows)} candidate tokens across the configured chains.")
    print(f"Primary watchlist: {recommendation.primary_symbol} [{recommendation.primary_chain}]")
    print()
    print("=== Reason ===")
    print(recommendation.thesis)
    for item in recommendation.why_now:
        print(f"- {item}")
    print()
    print("=== Risk ===")
    for item in recommendation.watchouts:
        print(f"- {item}")
    print()
    print("=== Next Action ===")
    for item in recommendation.next_actions:
        print(f"- {item}")
    print()
    print("=== Ranked List ===")
    for i, row in enumerate(rows[:10], 1):
        flags = ", ".join(row_value(row, "risk_flags", []) or []) or "no obvious risk flags"
        print(
            f"{i:02d}. [{row_value(row, 'chain', 'unknown')}] {row_value(row, 'symbol', '?')} | "
            f"score {float(row_value(row, 'score', 0.0)):.2f} | 24h {float(row_value(row, 'price_change_24h_pct', 0.0)):.2f}% | risk: {flags}"
        )


async def mcp_probe(url: str) -> None:
    async with BinanceMCPClient(url) as client:
        print(json.dumps(await client.probe(), ensure_ascii=False, indent=2))


async def mcp_list_tools(url: str) -> None:
    async with BinanceMCPClient(url) as client:
        tools = await client.list_tools()
        for i, tool in enumerate(tools, 1):
            title = f" | {tool.title}" if tool.title else ""
            desc = f" | {tool.description}" if tool.description else ""
            print(f"{i:02d}. {tool.name}{title}{desc}")


async def mcp_call(url: str, tool_name: str, args_json: str) -> None:
    async with BinanceMCPClient(url) as client:
        payload = json.loads(args_json or "{}")
        result = await client.call_tool(tool_name, payload)
        print(render_tool_result(result))


async def mcp_discover(url: str, keywords: list[str]) -> None:
    async with BinanceMCPClient(url) as client:
        tools = await client.list_tools()
        matches = client.search_tools(tools, keywords)
        if not matches:
            print("No matching Binance MCP tools found.")
            return

        for i, tool in enumerate(matches, 1):
            title = f" | {tool.title}" if tool.title else ""
            desc = f" | {tool.description}" if tool.description else ""
            print(f"{i:02d}. {tool.name}{title}{desc}")


async def mcp_market(url: str, symbols: list[str], interval: str, limit: int) -> None:
    async with BinanceMCPClient(url) as client:
        for symbol in symbols:
            tool, args, result = await client.market_snapshot(symbol, interval=interval, limit=limit)
            print(summarize_tool_call(tool, args, result))


async def mcp_symbol_detail(url: str, symbols: list[str]) -> None:
    async with BinanceMCPClient(url) as client:
        for symbol in symbols:
            tool, args, result = await client.symbol_detail(symbol)
            print(summarize_tool_call(tool, args, result))


async def mcp_kline(url: str, symbols: list[str], interval: str, limit: int) -> None:
    async with BinanceMCPClient(url) as client:
        for symbol in symbols:
            tool, args, result = await client.kline_data(symbol, interval=interval, limit=limit)
            print(summarize_tool_call(tool, args, result))


async def mcp_discover_price(url: str, fiat_currency: str) -> None:
    async with BinanceMCPClient(url) as client:
        tool, args, result = await client.discover_price(fiat_currency=fiat_currency)
        print(summarize_tool_call(tool, args, result))


async def mcp_account(url: str) -> None:
    async with BinanceMCPClient(url) as client:
        tool, args, result = await client.account_snapshot()
        print(summarize_tool_call(tool, args, result))


def run_mcp_task(coro: Any) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError as exc:
        print(f"error: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only BSC/Solana/Robinhood meme hotspot radar")
    parser.add_argument("--chains", default="bsc,solana,robinhood")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--agent", action="store_true", help="Render an agent-style observe/reason/report cycle.")
    parser.add_argument("--mcp-url", default=os.getenv("BINANCE_MCP_URL", DEFAULT_BINANCE_MCP_URL))
    parser.add_argument("--mcp-probe", action="store_true", help="Verify the Binance MCP connection and print tool metadata.")
    parser.add_argument("--mcp-list-tools", action="store_true", help="List tools exposed by the Binance MCP server.")
    parser.add_argument("--mcp-discover", nargs="+", help="Find Binance MCP tools that match one or more keywords.")
    parser.add_argument("--mcp-market", nargs="+", help="Call the best matching Binance MCP market-data tool for one or more symbols.")
    parser.add_argument("--mcp-symbol-detail", nargs="+", help="Call the official Binance MCP symbol detail tool for one or more symbols.")
    parser.add_argument("--mcp-kline", nargs="+", help="Call the official Binance MCP kline tool for one or more symbols.")
    parser.add_argument("--mcp-interval", default="1d", help="Interval used when the chosen MCP tool accepts one.")
    parser.add_argument("--mcp-limit", type=int, default=1, help="Limit used when the chosen MCP tool accepts one.")
    parser.add_argument("--mcp-fiat-currency", default="AED", help="Fiat currency used for discover price calls.")
    parser.add_argument("--mcp-account", action="store_true", help="Call the best matching Binance MCP account or balance tool.")
    parser.add_argument("--mcp-discover-price", action="store_true", help="Call the official Binance MCP discover price tool.")
    parser.add_argument("--mcp-call", help="Call a Binance MCP tool by name.")
    parser.add_argument("--mcp-args", default="{}", help="JSON arguments for --mcp-call.")
    args = parser.parse_args()

    if args.mcp_probe:
        run_mcp_task(mcp_probe(args.mcp_url))
        return

    if args.mcp_list_tools:
        run_mcp_task(mcp_list_tools(args.mcp_url))
        return

    if args.mcp_discover:
        run_mcp_task(mcp_discover(args.mcp_url, args.mcp_discover))
        return

    if args.mcp_market:
        run_mcp_task(mcp_market(args.mcp_url, args.mcp_market, args.mcp_interval, args.mcp_limit))
        return

    if args.mcp_symbol_detail:
        run_mcp_task(mcp_symbol_detail(args.mcp_url, args.mcp_symbol_detail))
        return

    if args.mcp_kline:
        run_mcp_task(mcp_kline(args.mcp_url, args.mcp_kline, args.mcp_interval, args.mcp_limit))
        return

    if args.mcp_account:
        run_mcp_task(mcp_account(args.mcp_url))
        return

    if args.mcp_discover_price:
        run_mcp_task(mcp_discover_price(args.mcp_url, args.mcp_fiat_currency))
        return

    if args.mcp_call:
        run_mcp_task(mcp_call(args.mcp_url, args.mcp_call, args.mcp_args))
        return

    chains = {x.strip().lower() for x in args.chains.split(",") if x.strip() in SUPPORTED}

    try:
        rows = [asdict(x) for x in fetch(chains)[: max(1, args.limit)]]
    except Exception as exc:
        rows = [{"error": str(exc), "hint": "data source temporarily unavailable; try again later."}]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if args.agent:
        render_agent_report(rows)
        return

    for i, row in enumerate(rows, 1):
        if "error" in row:
            print(f"error: {row['error']}")
            continue

        flags = ", ".join(row["risk_flags"]) or "no obvious risk flags"
        print(
            f"{i:02d}. [{row['chain']}] {row['symbol']} | "
            f"score {row['score']:.2f} | 24h {row['price_change_24h_pct']:.2f}% | risk: {flags}"
        )


if __name__ == "__main__":
    main()
