# 交易策略助手

基于 **Gradio + efinance + Plotly** 的交易策略研究服务。当前包含两个模块：

1. `数据获取`：下载 A 股 ETF、场内基金或个股日线行情，保存 CSV，并支持基于本地最新交易日增量更新。
2. `技术图表`：读取下载后的 CSV 或上传 CSV，绘制 K线、移动平均线、BOLL、成交量、MACD 和 RSI。

## 工程结构

```text
.
├── app.py
├── src/
│   ├── common/
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── models.py
│   │   └── validators.py
│   ├── service/
│   │   ├── market_data_service.py
│   │   ├── technical_analysis_service.py
│   │   ├── technical_indicator_service.py
│   │   └── ports.py
│   ├── infra/
│   │   ├── market_data/
│   │   │   └── efinance_gateway.py
│   │   ├── storage/
│   │   │   └── csv_repository.py
│   │   └── charting/
│   │       └── plotly_chart_builder.py
│   └── ui/
│       ├── app_builder.py
│       └── tabs/
│           ├── tab1_data_fetch.py
│           └── tab2_technical_chart.py
├── tests/
├── outputs/
└── pyproject.toml
```

依赖方向：

```text
UI -> Service -> Common
       ^
       |
     Infra
```

`app.py` 只负责组装依赖。业务编排不直接依赖 efinance、Plotly 或具体文件系统实现。

## 数据获取

- 输入六位 ETF、场内基金或个股代码
- 支持自动识别、ETF、股票
- 支持不复权、前复权、后复权
- 自定义开始日期和结束日期
- 最近 200 行预览
- 完整 CSV 下载
- “更新至最新”按钮：读取本地最新 CSV，从最后交易日拉取至今天，合并去重后原子覆盖原文件
- 更新时自动沿用 CSV 中的资产类型与复权口径
- 输入校验、上游重试、OHLC 质量检查

服务调用：

```python
import efinance as ef

ef.stock.get_quote_history(
    "510300",
    beg="20160723",
    end="20260723",
    klt=101,
    fqt=0,
    suppress_error=True,
)
```

`klt=101` 表示日线，`fqt=0/1/2` 分别表示不复权、前复权、后复权。

## 技术图表

### 数据选择

- 输入证券代码且不上传文件：从 `outputs/` 查找该代码最新生成的 CSV。
- 上传 CSV：优先读取上传文件。
- 上传文件只有一个证券时，证券代码可以留空。
- CSV 含多个证券时，必须输入代码进行过滤。

CSV 至少需要以下字段：

```text
trade_date,open,high,low,close,volume
```

由“数据获取”生成的 CSV 可以直接使用。

### 图表面板

1. K线和 MA5、MA10、MA20、MA60、MA250、MA360
2. BOLL K线及上轨、中轨、下轨
3. 成交量
4. MACD、Signal 和 MACD 柱状图
5. RSI 和 30/70 参考线

默认采用 A 股颜色约定：上涨红、下跌绿。横轴使用 CSV 中实际存在的交易日期作为离散分类轴，因此周末、节假日和其他休市日期不会产生空白。图表支持缩放、拖动和统一悬停提示。

### 默认指标参数

| 指标 | 默认参数 |
|---|---|
| 移动平均线 | MA5、MA10、MA20、MA60、MA250、MA360 |
| MACD | 12、26、9 |
| BOLL | 20日、2倍总体标准差 |
| RSI | 14日 Wilder 平滑 |
| 显示条数 | 最近250个交易日 |

指标先在完整数据上计算，再应用日期和显示条数过滤，避免只读取最近250行导致指标缺少预热期。MA250 和 MA360 分别需要至少250和360个交易日的数据；历史不足时对应均线为空。

## 本地运行

要求 Python 3.10 或更高版本。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Linux / macOS：

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

浏览器打开：

```text
http://127.0.0.1:8888
```

`app.py` 会自动把 `src/` 加入 Python 模块搜索路径，因此从工程根目录执行即可。

## Docker

```bash
docker compose up --build
```

生成的 CSV 会持久化到本机 `outputs/`。

## CSV 数据约定

1. efinance 的历史成交量按“手”处理，默认乘以100转换为股或基金份额，并保留原始值。
2. `pre_close` 优先使用 `close - change` 还原，缺失时使用上一条收盘价。
3. 百分比字段存为小数，例如 `2.5%` 保存为 `0.025`。
4. 复权模式下，OHLC 是复权口径，成交量与成交额仍是实际成交口径。
5. CSV 使用 UTF-8 BOM，可直接用 Excel 打开。
6. CSV 读取时将 `symbol` 作为字符串保存，避免 `000001` 被转换为 `1`。
7. 自动识别基于常见证券代码规则，特殊场内基金可手动选择 ETF。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

测试不访问网络，覆盖输入校验、行情标准化、CSV 读写、指标计算、图表轨迹、业务编排和 Gradio Tab 注册。

## 环境变量

参见 `.env.example`：

- `GRADIO_SERVER_NAME`
- `GRADIO_SERVER_PORT`
- `GRADIO_SHARE`
- `OUTPUT_DIR`
- `A_SHARE_LOT_SIZE`
- `OUTPUT_RETENTION_HOURS`
- `FETCH_ATTEMPTS`
- `RETRY_BASE_DELAY_SECONDS`

## 风险说明

该工程用于研究与策略验证。efinance 的公开行情上游可能出现限流、连接超时、字段变化或历史修订；正式回测前应固定数据快照并进行多源核验。技术指标仅用于研究，不构成投资建议。
