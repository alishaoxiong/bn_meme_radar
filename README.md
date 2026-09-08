# Meme Radar Agent

一个只读的多链 Meme 热点雷达 MVP，已经加上 Binance MCP 的自动发现和业务调用入口。

## 能做什么

- 抓取 BSC、Solana、Robinhood Chain 的公开 DEX 热点数据。
- 以成交量、流动性、价格动量、买卖流和公开资料生成透明分数。
- 输出热点榜单和基础风险标签。
- 通过官方 Binance MCP endpoint 验证连接、列出工具、自动发现、调用行情和账户类工具。
- 全程不连接私钥，不签名，不下单。

## 快速运行

```powershell
python meme_radar.py --chains bsc,solana --limit 10
python meme_radar.py --json > hotspots.json
```

## Binance MCP 接入

官方 MCP endpoint：

`https://agent.binance.com/mcp/agentic`

先安装依赖：

```powershell
pip install -r requirements.txt
```

然后验证连接：

```powershell
python meme_radar.py --mcp-probe
python meme_radar.py --mcp-list-tools
python meme_radar.py --mcp-discover ticker price balance
python meme_radar.py --mcp-symbol-detail BTCUSDT
python meme_radar.py --mcp-kline BTCUSDT
python meme_radar.py --mcp-market BTCUSDT
python meme_radar.py --mcp-discover-price
python meme_radar.py --mcp-account
python meme_radar.py --mcp-call <tool_name> --mcp-args "{}"
```

如果你的 Agent 环境已经配置了 `BINANCE_MCP_URL`，也可以直接省略 `--mcp-url`。

## 说明

- 这个仓库默认还是只读分析模式。
- Binance MCP 的具体工具名会随账号权限和产品能力变化，所以我把入口做成了官方工具优先调用，再回退自动匹配。
- 如果 MCP 未安装，原始雷达命令仍然可以运行。
