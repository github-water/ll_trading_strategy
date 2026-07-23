# 交易策略助手分层重构设计

## 目标

将现有 Gradio 行情下载功能重构为 `src` 布局，以 `ui`、`service`、`common`、`infra` 四层隔离职责，并将首个功能命名为 `Tab1 数据获取`。

## 依赖方向

- `ui` 仅依赖 `service` 与 `common`，负责 Gradio 组件和展示转换。
- `service` 依赖 `common` 与抽象端口，负责校验、流程编排、日期过滤和结果组装。
- `infra` 实现行情网关与 CSV 存储端口，封装 efinance 和文件系统。
- `common` 不依赖 Gradio、efinance 或具体存储，保存配置、常量、异常、领域模型和校验函数。
- `app.py` 是唯一的依赖组装入口。

## Tab1 数据获取

输入证券代码、资产类型、日期范围和复权方式，调用 `MarketDataService`。成功时返回最近 200 行倒序预览、状态摘要和完整 CSV；失败时将领域错误转换为可读提示，不把第三方异常传播到 UI。

## 数据口径

使用 `ef.stock.get_quote_history` 获取股票、ETF 和场内基金日线。成交量按手转换为股或基金份额，保留原始手数；比例字段统一存为小数；CSV 使用 UTF-8 BOM；复权 OHLC 与实际成交量、成交额的口径差异以 warning 标注。

## 测试

网络请求通过注入 fetcher 替代，测试覆盖公共校验、服务编排、efinance 映射与重试、CSV 持久化和 Tab1 回调。完整测试不能访问网络。
