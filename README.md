# stock_bro

每日股票数据统计系统的基础采集模块。

当前已实现 A 股每日涨停个股数据采集，数据源为东方财富涨停池公开接口。采集结果可保存为 CSV、JSONL，并可同步写入 SQLite，便于后续做统计分析和报表。默认排除名称以 `ST`、`*ST`、`S*ST` 开头的个股。

注意：该公开接口主要适合采集当天涨停池。历史日期可能返回空数据，建议用定时任务每天收盘后执行并保存本地归档。

## 使用方式

采集指定日期：

```powershell
python -m stock_bro.cli limit-up --date 2026-05-11
```

采集今天：

```powershell
python -m stock_bro.cli limit-up
```

默认输出：

- `data/limit_up/YYYYMMDD.csv`
- `data/limit_up/YYYYMMDD.jsonl`
- `data/stock_bro.sqlite3`

只保存 CSV，不写 SQLite：

```powershell
python -m stock_bro.cli limit-up --date 2026-05-11 --no-sqlite
```

如需包含 ST 个股：

```powershell
python -m stock_bro.cli limit-up --date 2026-05-11 --include-st
```

指定输出目录和数据库：

```powershell
python -m stock_bro.cli limit-up --date 2026-05-11 --out-dir output/limit_up --sqlite output/stocks.sqlite3
```

命令执行后会额外打印炸板统计：`failed_limit_up_times > 0` 的股票会被列为炸板股，并按 `change_percent` 统计收盘在昨收价上、昨收价、昨收价以下或未知。

采集开盘啦公开接口数据：

```powershell
python -m stock_bro.cli kaipanla --dataset all
```

可选数据集：

- `sentiment`：市场情绪和涨停数量
- `sharp-withdrawal`：急跌/炸板相关实时列表
- `daily-limit-performance`：历史涨停表现，支持 `--date YYYY-MM-DD`
- `block-limit-up`：按题材板块聚合的涨停股列表，支持 `--date YYYY-MM-DD`
- `dragon-tiger`：龙虎榜列表

默认输出到 `data/kaipanla/YYYYMMDD_<dataset>.json`。

对比东方财富和开盘啦本地归档：

```powershell
python -m stock_bro.cli compare-limit-up --date 2026-05-11
```

该命令按股票代码对比 `data/limit_up/YYYYMMDD.jsonl` 和开盘啦本地归档，优先使用 `data/kaipanla/YYYYMMDD_block_limit_up.json`，没有该文件时回退到 `data/kaipanla/YYYYMMDD_daily_limit_performance.json`，打印两边数量、交集数量，以及各自独有股票。

获取并缓存 A 股交易日历：

```powershell
python -m stock_bro.cli trade-calendar
```

看板索引会读取 `data/trade_calendar.json`，只展示交易日且有涨停数据的日期。

## 字段说明

CSV 和 SQLite 表 `limit_up_stocks` 使用相同的标准字段：

| 字段 | 含义 |
| --- | --- |
| trade_date | 交易日期，`YYYY-MM-DD` |
| code | 股票代码 |
| name | 股票名称 |
| latest_price | 最新价 |
| change_percent | 涨跌幅，百分比 |
| turnover_amount | 成交额，元 |
| limit_up_amount | 封板资金，元 |
| first_limit_up_time | 首次封板时间，`HH:MM:SS` |
| last_limit_up_time | 最后封板时间，`HH:MM:SS` |
| consecutive_limit_up_days | 连板数 |
| failed_limit_up_times | 炸板次数 |
| limit_up_session | 按最后一次封板时间划分：`opening` 开盘涨停、`morning_9_to_10` 9 点到 10 点涨停、`morning_10_to_1130` 10 点到 11:30 涨停、`afternoon_1130_to_1430` 11:30 到 14:30 涨停、`late_afternoon_after_1430` 14:30 以后涨停、`unknown` 无有效最后封板时间 |
| industry | 所属行业 |
| raw | 原始接口字段 JSON，便于排查数据源变动 |
| collected_at | 采集时间，UTC ISO 格式 |

## 测试

```powershell
python -m unittest discover -s tests
```
