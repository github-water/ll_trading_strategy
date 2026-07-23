from __future__ import annotations

from typing import Callable

import gradio as gr
import pandas as pd

from common.backtest_models import BacktestConfig, BacktestRequest, PositionSizingMode
from common.exceptions import BacktestError, MarketDataError, StrategyError
from service.backtest_service import BacktestService


POSITION_MODE_LABELS = {
    "全仓交易": PositionSizingMode.FULL,
    "ATR风险仓位": PositionSizingMode.ATR_RISK,
}


def position_mode_from_label(label: str) -> PositionSizingMode:
    try:
        return POSITION_MODE_LABELS[str(label)]
    except KeyError as exc:
        raise ValueError(f"未知仓位管理方式：{label}") from exc


def build_metrics_table(metrics: dict) -> pd.DataFrame:
    rows = [
        ("初始资金", metrics.get("initial_cash"), "元"),
        ("最终资产", metrics.get("final_equity"), "元"),
        ("累计收益率", metrics.get("cumulative_return"), "%"),
        ("年化收益率", metrics.get("annualized_return"), "%"),
        ("基准累计收益率", metrics.get("benchmark_cumulative_return"), "%"),
        ("超额收益率", metrics.get("excess_return"), "%"),
        ("最大回撤", metrics.get("maximum_drawdown"), "%"),
        ("已完成交易次数", metrics.get("completed_trades"), "次"),
        ("胜率", metrics.get("win_rate"), "%"),
        ("盈亏比", metrics.get("profit_loss_ratio"), ""),
        ("平均持仓天数", metrics.get("average_holding_days"), "天"),
        ("佣金总额", metrics.get("commission_total"), "元"),
        ("滑点成本", metrics.get("slippage_cost"), "元"),
        ("未平仓浮动盈亏", metrics.get("unrealized_profit"), "元"),
    ]
    output: list[dict[str, object]] = []
    percentage_names = {
        "累计收益率", "年化收益率", "基准累计收益率", "超额收益率", "最大回撤", "胜率"
    }
    for name, raw, unit in rows:
        value = raw
        if value is None:
            display = "-"
        elif name in percentage_names:
            display = f"{float(value) * 100:.2f}%"
        elif name in {"初始资金", "最终资产", "佣金总额", "滑点成本", "未平仓浮动盈亏"}:
            display = f"{float(value):,.2f} 元"
        elif name == "盈亏比":
            display = "∞" if value == float("inf") else f"{float(value):.2f}"
        elif name == "已完成交易次数":
            display = f"{int(value)} 次"
        else:
            display = f"{float(value):.2f} {unit}".strip()
        output.append({"指标": name, "结果": display})
    output.extend(
        [
            {"指标": "CSV价格口径", "结果": str(metrics.get("price_adjustment", "未知"))},
            {"指标": "现金分红", "结果": "未计入"},
        ]
    )
    return pd.DataFrame(output)


def build_open_position_table(open_position: dict) -> pd.DataFrame:
    if not open_position:
        return pd.DataFrame([{"状态": "无未平仓持仓"}])
    return pd.DataFrame(
        [
            {
                "买入日期": open_position.get("buy_date"),
                "买入价": open_position.get("buy_price"),
                "数量": open_position.get("quantity"),
                "持仓成本": open_position.get("cost"),
                "期末市值": open_position.get("market_value"),
                "浮动盈亏": open_position.get("unrealized_profit"),
                "当前止损价": open_position.get("stop_price"),
            }
        ]
    )


def build_status(result) -> str:
    metrics = result.metrics
    warning = ""
    if metrics.get("calendar_days", 0) < 180:
        warning = "\n- ⚠️ 回测自然天数少于180天，年化收益可能失真。"
    return "\n".join(
        [
            "### 回测完成",
            f"- 标的：`{result.symbol}`",
            f"- 策略：**{result.strategy_name}**",
            f"- 数据文件：`{result.source_path.name}`",
            f"- 初始资金：**{result.config.initial_cash:,.2f} 元**",
            f"- 最终资产：**{metrics['final_equity']:,.2f} 元**",
            f"- 年化收益率：**{metrics['annualized_return'] * 100:.2f}%**",
            "- 价格口径：严格使用CSV，不额外复权；未计入现金分红。",
        ]
    ) + warning


def create_backtest_handler(service: BacktestService) -> Callable[..., tuple]:
    def handle(
        symbol: str,
        csv_path: str | None,
        strategy_id: str,
        start_date: str,
        end_date: str,
        initial_cash: int | float,
        position_mode_label: str,
        risk_per_trade_percent: int | float,
        maximum_position_percent: int | float,
        override_atr: bool,
        atr_period: int | float,
        initial_atr_multiple: int | float,
        trailing_atr_multiple: int | float,
        commission_percent: int | float,
        minimum_commission: int | float,
        buy_slippage_percent: int | float,
        sell_slippage_percent: int | float,
        limit_percent: int | float,
    ) -> tuple:
        try:
            config = BacktestConfig(
                initial_cash=float(initial_cash),
                position_mode=position_mode_from_label(position_mode_label),
                risk_per_trade=float(risk_per_trade_percent) / 100.0,
                maximum_position=float(maximum_position_percent) / 100.0,
                commission_rate=float(commission_percent) / 100.0,
                minimum_commission=float(minimum_commission),
                buy_slippage=float(buy_slippage_percent) / 100.0,
                sell_slippage=float(sell_slippage_percent) / 100.0,
                stamp_duty=0.0,
                lot_size=100,
                limit_ratio=float(limit_percent) / 100.0,
                atr_period_override=int(atr_period) if override_atr else None,
                initial_atr_multiple_override=(
                    float(initial_atr_multiple) if override_atr else None
                ),
                trailing_atr_multiple_override=(
                    float(trailing_atr_multiple) if override_atr else None
                ),
            )
            result = service.run(
                BacktestRequest(
                    symbol=symbol,
                    csv_path=csv_path,
                    strategy_id=strategy_id,
                    start_date=start_date,
                    end_date=end_date,
                    config=config,
                )
            )
            return (
                result.price_figure,
                result.equity_figure,
                result.drawdown_figure,
                build_metrics_table(result.metrics),
                build_open_position_table(result.open_position),
                result.trades,
                result.events,
                build_status(result),
            )
        except (BacktestError, MarketDataError, StrategyError, ValueError) as exc:
            empty = pd.DataFrame()
            return None, None, None, empty, empty, empty, empty, f"### 回测失败\n\n{exc}"
        except Exception as exc:
            empty = pd.DataFrame()
            return (
                None,
                None,
                None,
                empty,
                empty,
                empty,
                empty,
                f"### 系统错误\n\n{type(exc).__name__}: {exc}",
            )

    return handle


def build_backtest_tab(service: BacktestService) -> None:
    strategy_choices = service.list_strategy_choices()
    default_strategy = strategy_choices[0][1] if strategy_choices else None

    with gr.Tab("数据回测"):
        gr.Markdown(
            """
## 单标的策略回测

选择本地下载或上传的CSV与交易策略，按日线信号执行回测。普通信号在收盘后确认、
下一交易日开盘成交；ATR止损支持盘中触发。严格使用CSV价格，不额外复权，暂不计现金分红。
"""
        )
        with gr.Row():
            symbol_input = gr.Textbox(label="证券代码", value="510300", scale=2)
            csv_input = gr.File(
                label="上传CSV（可选，优先使用）",
                file_types=[".csv"],
                type="filepath",
                scale=3,
            )
            strategy_input = gr.Dropdown(
                label="交易策略",
                choices=strategy_choices,
                value=default_strategy,
                scale=3,
            )
        with gr.Row():
            start_date_input = gr.Textbox(label="开始日期（可选）", placeholder="YYYY-MM-DD")
            end_date_input = gr.Textbox(label="结束日期（可选）", placeholder="YYYY-MM-DD")
            initial_cash_input = gr.Number(label="初始资金（元）", value=100000, precision=2)
            position_mode_input = gr.Radio(
                label="仓位管理",
                choices=list(POSITION_MODE_LABELS),
                value="全仓交易",
            )

        with gr.Accordion("ATR风险仓位参数", open=True):
            with gr.Row():
                risk_per_trade_input = gr.Number(label="单笔风险（%）", value=1.0)
                maximum_position_input = gr.Number(label="最大仓位（%）", value=30.0)
                override_atr_input = gr.Checkbox(label="覆盖策略ATR参数", value=False)
            with gr.Row():
                atr_period_input = gr.Number(label="ATR周期", value=14, precision=0)
                initial_atr_multiple_input = gr.Number(label="初始止损倍数", value=2.5)
                trailing_atr_multiple_input = gr.Number(label="移动止损倍数", value=3.5)

        with gr.Accordion("交易成本与成交限制", open=False):
            with gr.Row():
                commission_input = gr.Number(label="佣金率（%）", value=0.03)
                minimum_commission_input = gr.Number(label="最低佣金（元）", value=5.0)
                buy_slippage_input = gr.Number(label="买入滑点（%）", value=0.05)
                sell_slippage_input = gr.Number(label="卖出滑点（%）", value=0.05)
                limit_ratio_input = gr.Number(label="涨跌停比例（%）", value=10.0)

        run_button = gr.Button("运行回测", variant="primary")
        status_output = gr.Markdown("尚未运行回测。")
        metrics_output = gr.Dataframe(label="核心指标", interactive=False)
        open_position_output = gr.Dataframe(label="期末未平仓持仓", interactive=False)
        price_output = gr.Plot(label="K线与买卖点")
        equity_output = gr.Plot(label="交易曲线")
        drawdown_output = gr.Plot(label="回撤曲线")
        trades_output = gr.Dataframe(label="已完成交易明细", interactive=False)
        events_output = gr.Dataframe(label="订单与事件日志", interactive=False)

        run_button.click(
            fn=create_backtest_handler(service),
            inputs=[
                symbol_input,
                csv_input,
                strategy_input,
                start_date_input,
                end_date_input,
                initial_cash_input,
                position_mode_input,
                risk_per_trade_input,
                maximum_position_input,
                override_atr_input,
                atr_period_input,
                initial_atr_multiple_input,
                trailing_atr_multiple_input,
                commission_input,
                minimum_commission_input,
                buy_slippage_input,
                sell_slippage_input,
                limit_ratio_input,
            ],
            outputs=[
                price_output,
                equity_output,
                drawdown_output,
                metrics_output,
                open_position_output,
                trades_output,
                events_output,
                status_output,
            ],
            api_name="run_backtest",
        )
