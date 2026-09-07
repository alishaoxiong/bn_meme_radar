# Meme Radar Agent

一个只读的多链 Meme 热点雷达 MVP，面向 Binance Agent OS 迷你黑客松“搭 Agent”赛道。

## 能做什么

- 抓取 BSC、Solana 的公开 DEX 热点数据；
- 以成交量/流动性、价格动量、买卖流、社区资料和 Boost 做透明的热点分数；
- 输出类似资讯流的热点卡片，并附基础风险标签；
- Robinhood Chain：Chain ID `4663`、原生币 ETH，尝试读取 DexScreener 的 `robinhood` 链数据；也可通过 `MEME_RADAR_RH_URL` 接入自定义只读 JSON 数据源；
- 明确不连接私钥、不签名、不下单。

## 快速运行

```bash
python meme_radar.py --chains bsc,solana --limit 10
python meme_radar.py --json > hotspots.json
```

Robinhood 官方连接文档：[docs.robinhood.com/chain/connecting](https://docs.robinhood.com/chain/connecting/)。公开 RPC 为 `https://rpc.mainnet.chain.robinhood.com`，官方说明该端点有速率限制，生产环境可改用 Alchemy/QuickNode 等索引服务。

如需自定义 Robinhood 热点数据源，需提供类似 `{ "pairs": [ ... ] }` 的只读 JSON，并设置：

```bash
$env:MEME_RADAR_RH_URL = "https://your-readonly-rh-feed.example/pairs"
python meme_radar.py --chains robinhood
```

## Agent OS 演示提示词

> 每 10 分钟抓取 BSC、Solana、Robinhood Chain 的公开 Meme 数据，生成“今日 Meme 热点”资讯流。每条包含：链、代币、热度分数、24h 涨跌、流动性、成交量、买卖笔数、风险标签和数据来源。只读分析，不执行交易；如果数据源不可用，明确标注，不要编造数据。

## 提交材料建议

1. GitHub 仓库链接；
2. 60–90 秒 Demo：输入“今日 Meme 热点”，展示三链榜单和风险标签；
3. README 中说明评分公式、数据源、Robinhood 适配器和“不下单”安全边界；
4. 在活动帖下回复/引用提交作品，再填写官方表单。

> 分数是信息筛选启发式，不是投资建议；Meme 代币可能存在极高波动、流动性枯竭和合约风险。
