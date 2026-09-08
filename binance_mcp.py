"""Thin Binance MCP client wrapper.

This module keeps the repo usable in two modes:
- read-only meme radar without extra dependencies
- Binance MCP connectivity when the MCP SDK is installed
"""

from __future__ import annotations

import json
import os
import time
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

DEFAULT_BINANCE_MCP_URL = "https://agent.binance.com/mcp/agentic"

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # pragma: no cover - optional dependency
    ClientSession = None
    streamable_http_client = None


@dataclass
class McpTool:
    name: str
    description: str | None = None
    title: str | None = None
    input_schema: dict[str, Any] | None = None


class BinanceMCPClient:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("BINANCE_MCP_URL", DEFAULT_BINANCE_MCP_URL)
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "BinanceMCPClient":
        if ClientSession is None or streamable_http_client is None:
            raise RuntimeError(
                "MCP SDK is not installed. Run `pip install -r requirements.txt` first."
            )

        read_stream, write_stream = await self._stack.enter_async_context(
            streamable_http_client(self.url)
        )
        self.session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._stack.aclose()

    async def list_tools(self) -> list[McpTool]:
        if self.session is None:
            raise RuntimeError("MCP session is not initialized.")

        result = await self.session.list_tools()
        return [
            McpTool(
                name=tool.name,
                description=getattr(tool, "description", None),
                title=getattr(tool, "title", None),
                input_schema=getattr(tool, "input_schema", None),
            )
            for tool in result.tools
        ]

    @staticmethod
    def _haystack(tool: McpTool) -> str:
        parts = [tool.name, tool.title or "", tool.description or "", json.dumps(tool.input_schema or {}, ensure_ascii=False)]
        return " ".join(parts).lower()

    def search_tools(self, tools: Sequence[McpTool], keywords: Iterable[str]) -> list[McpTool]:
        needles = [k.strip().lower() for k in keywords if k and k.strip()]
        scored: list[tuple[int, int, McpTool]] = []
        for index, tool in enumerate(tools):
            hay = self._haystack(tool)
            score = sum(1 for needle in needles if needle in hay)
            if score:
                required = len((tool.input_schema or {}).get("required") or [])
                scored.append((-score, required, index, tool))
        scored.sort()
        return [item[-1] for item in scored]

    @staticmethod
    def pick_exact_tool(tools: Sequence[McpTool], name: str) -> McpTool | None:
        target = name.strip().lower()
        for tool in tools:
            if tool.name.strip().lower() == target:
                return tool
        return None

    @staticmethod
    def _looks_like_symbol_key(name: str) -> bool:
        lowered = name.lower()
        return any(
            token in lowered
            for token in ("symbol", "pair", "ticker", "market", "asset", "coin", "contract", "instrument")
        )

    @staticmethod
    def _looks_like_interval_key(name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in ("interval", "period", "timeframe", "window"))

    @staticmethod
    def _looks_like_limit_key(name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in ("limit", "count", "size", "depth"))

    @staticmethod
    def _looks_like_account_key(name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in ("account", "wallet", "balance", "position", "portfolio"))

    def build_arguments(
        self,
        tool: McpTool,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        limit: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = tool.input_schema or {}
        props = schema.get("properties") or {}
        args: dict[str, Any] = dict(extra or {})

        for key, spec in props.items():
            if key in args:
                continue
            if symbol and self._looks_like_symbol_key(key):
                args[key] = symbol
                continue
            if interval and self._looks_like_interval_key(key):
                args[key] = interval
                continue
            if limit is not None and self._looks_like_limit_key(key):
                args[key] = limit
                continue

            default = spec.get("default")
            if default is not None:
                args[key] = default

        required = list(schema.get("required") or [])
        for key in required:
            if key in args:
                continue
            if symbol and self._looks_like_symbol_key(key):
                args[key] = symbol
            elif interval and self._looks_like_interval_key(key):
                args[key] = interval
            elif limit is not None and self._looks_like_limit_key(key):
                args[key] = limit

        return args

    @staticmethod
    def _kline_window(interval: str, limit: int) -> tuple[int, int]:
        now = int(time.time() * 1000)
        span_map = {
            "3m": 3 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }
        span = span_map.get(interval, span_map["1d"])
        bars = max(1, limit)
        end_time = now
        start_time = end_time - span * bars
        return start_time, end_time

    def build_exact_arguments(
        self,
        tool_name: str,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        limit: int | None = None,
        fiat_currency: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lowered = tool_name.lower()
        args = dict(extra or {})

        if "symbol detail" in lowered:
            if symbol:
                args.setdefault("cryptoCurrency", symbol)
        elif "kline" in lowered:
            if symbol:
                args.setdefault("cryptoCurrency", symbol)
            if interval:
                args.setdefault("interval", interval)
            start_time, end_time = self._kline_window(interval or "1d", limit or 1)
            args.setdefault("startTime", start_time)
            args.setdefault("endTime", end_time)
        elif "discover price" in lowered:
            args.setdefault("fiatCurrency", fiat_currency or "AED")
        elif "balance" in lowered:
            for key in ("userId", "walletId", "accountId"):
                if key in args:
                    break

        return args

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if self.session is None:
            raise RuntimeError("MCP session is not initialized.")

        return await self.session.call_tool(name, arguments or {})

    async def call_exact_or_best_tool(
        self,
        preferred_names: Sequence[str],
        keywords: Sequence[str],
        *,
        symbol: str | None = None,
        interval: str | None = None,
        limit: int | None = None,
        fiat_currency: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[McpTool, dict[str, Any], Any]:
        tools = await self.list_tools()

        for name in preferred_names:
            exact = self.pick_exact_tool(tools, name)
            if exact is None:
                continue
            args = self.build_exact_arguments(
                exact.name,
                symbol=symbol,
                interval=interval,
                limit=limit,
                fiat_currency=fiat_currency,
                extra=extra,
            )
            try:
                result = await self.call_tool(exact.name, args)
                return exact, args, result
            except Exception:
                continue

        matches = self.search_tools(tools, keywords)
        errors: list[str] = []
        for tool in matches:
            args = self.build_arguments(tool, symbol=symbol, interval=interval, limit=limit, extra=extra)
            try:
                result = await self.call_tool(tool.name, args)
                return tool, args, result
            except Exception as exc:  # pragma: no cover - depends on remote server
                errors.append(f"{tool.name}: {exc}")

        raise RuntimeError(
            "No Binance MCP tool matched the requested intent. "
            f"Preferred={list(preferred_names)!r}, keywords={list(keywords)!r}. Errors={errors[:3]!r}"
        )

    async def call_first_matching_tool(
        self,
        keywords: Sequence[str],
        *,
        symbol: str | None = None,
        interval: str | None = None,
        limit: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[McpTool, dict[str, Any], Any]:
        tools = await self.list_tools()
        matches = self.search_tools(tools, keywords)
        errors: list[str] = []

        for tool in matches:
            args = self.build_arguments(tool, symbol=symbol, interval=interval, limit=limit, extra=extra)
            try:
                result = await self.call_tool(tool.name, args)
                return tool, args, result
            except Exception as exc:  # pragma: no cover - depends on remote server
                errors.append(f"{tool.name}: {exc}")

        raise RuntimeError(
            "No Binance MCP tool matched the requested intent. "
            f"Keywords={list(keywords)!r}. Errors={errors[:3]!r}"
        )

    async def market_snapshot(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 1,
    ) -> tuple[McpTool, dict[str, Any], Any]:
        return await self.call_exact_or_best_tool(
            ["Get Symbol Detail", "Get Kline Data", "Get Discover Price"],
            ["ticker", "24h", "price", "bookticker", "book ticker", "kline", "candles", "depth"],
            symbol=symbol,
            interval=interval,
            limit=limit,
            fiat_currency="AED",
        )

    async def account_snapshot(self) -> tuple[McpTool, dict[str, Any], Any]:
        return await self.call_exact_or_best_tool(
            ["Get Balance"],
            ["balance", "account", "position", "wallet", "portfolio"],
        )

    async def symbol_detail(self, symbol: str) -> tuple[McpTool, dict[str, Any], Any]:
        return await self.call_exact_or_best_tool(
            ["Get Symbol Detail"],
            ["symbol detail", "market cap", "rank", "volume"],
            symbol=symbol,
        )

    async def kline_data(self, symbol: str, interval: str = "1d", limit: int = 1) -> tuple[McpTool, dict[str, Any], Any]:
        return await self.call_exact_or_best_tool(
            ["Get Kline Data"],
            ["kline", "candles", "chart"],
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

    async def discover_price(self, fiat_currency: str = "AED") -> tuple[McpTool, dict[str, Any], Any]:
        return await self.call_exact_or_best_tool(
            ["Get Discover Price"],
            ["discover price", "quotation", "fiat", "market data"],
            fiat_currency=fiat_currency,
        )

    async def probe(self) -> dict[str, Any]:
        tools = await self.list_tools()
        return {
            "endpoint": self.url,
            "tool_count": len(tools),
            "tools": [asdict(tool) for tool in tools],
        }


def render_tool_result(result: Any) -> str:
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False, indent=2, default=str)

    content = getattr(result, "content", None)
    if content:
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            parts.append(text if text is not None else str(block))
        return "\n".join(parts)

    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def summarize_tool_call(tool: McpTool, args: dict[str, Any], result: Any) -> str:
    payload = {
        "tool": tool.name,
        "title": tool.title,
        "arguments": args,
        "result": getattr(result, "structured_content", None) or getattr(result, "content", None),
        "is_error": getattr(result, "is_error", None),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
