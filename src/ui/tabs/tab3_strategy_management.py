from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import gradio as gr
import pandas as pd

from common.exceptions import StrategyError, StrategyValidationError
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from service.strategy_management_service import StrategyManagementService
from service.strategy_validator import FIELD_NAMES, INDICATOR_NAMES

OPERAND_CHOICES = sorted(FIELD_NAMES) + ["CONSTANT"] + sorted(INDICATOR_NAMES)
COMPARISON_CHOICES = [">", ">=", "<", "<=", "==", "CROSS_ABOVE", "CROSS_BELOW"]
RULE_TABLE_COLUMNS = ["序号", "启用", "分组", "组内逻辑", "条件"]
STRATEGY_TABLE_COLUMNS = [
    "策略名称",
    "资产类型",
    "周期",
    "状态",
    "入场条件",
    "退出条件",
    "只读",
    "更新时间",
]


def _parse_json_object(value: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "{}").strip() or "{}"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StrategyValidationError(f"参数必须是合法 JSON：{exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise StrategyValidationError("参数 JSON 必须是对象，例如 {\"period\": 20}。")
    return parsed


def parse_operand(name: str, params_text: str | dict[str, Any] | None) -> Operand:
    params = _parse_json_object(params_text)
    if name in FIELD_NAMES:
        return Operand.field(name)
    if name == "CONSTANT":
        if "value" not in params:
            raise StrategyValidationError("常数参数必须包含 value，例如 {\"value\": 20}。")
        return Operand.constant(params["value"])
    if name in INDICATOR_NAMES:
        return Operand.indicator(name, params)
    raise StrategyValidationError(f"不支持的操作数：{name}")


def operand_summary(operand: Operand) -> str:
    if operand.kind == "field":
        return operand.name
    if operand.kind == "constant":
        return str(operand.params.get("value"))
    params = ", ".join(f"{key}={value}" for key, value in operand.params.items())
    return f"{operand.name}({params})" if params else operand.name


def rule_summary(rule: StrategyRule) -> str:
    operator = {
        "CROSS_ABOVE": "上穿",
        "CROSS_BELOW": "下穿",
    }.get(rule.operator, rule.operator)
    return f"{operand_summary(rule.left)} {operator} {operand_summary(rule.right)}"


def _rules_from_state(state: list[dict[str, Any]] | list[StrategyRule] | None) -> list[StrategyRule]:
    rules: list[StrategyRule] = []
    for item in state or []:
        if isinstance(item, StrategyRule):
            rules.append(item)
        else:
            rules.append(StrategyRule.from_dict(dict(item)))
    return rules


def _rules_to_state(rules: list[StrategyRule]) -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in rules]


def build_rule_table(state: list[dict[str, Any]] | list[StrategyRule] | None) -> pd.DataFrame:
    rules = _rules_from_state(state)
    rows = [
        {
            "序号": index,
            "启用": "是" if rule.enabled else "否",
            "分组": rule.group,
            "组内逻辑": rule.group_operator,
            "条件": rule_summary(rule),
        }
        for index, rule in enumerate(rules, start=1)
    ]
    return pd.DataFrame(rows, columns=RULE_TABLE_COLUMNS)


def build_strategy_table(strategies: list[TradingStrategy]) -> pd.DataFrame:
    rows = [
        {
            "策略名称": item.name,
            "资产类型": item.asset_type,
            "周期": item.timeframe,
            "状态": "启用" if item.enabled else "停用",
            "入场条件": sum(rule.enabled for rule in item.entry_rule.rules),
            "退出条件": sum(rule.enabled for rule in item.exit_rule.rules),
            "只读": "是" if item.is_builtin else "否",
            "更新时间": item.updated_at,
        }
        for item in strategies
    ]
    return pd.DataFrame(rows, columns=STRATEGY_TABLE_COLUMNS)


def append_or_update_rule(
    entry_state: list[dict[str, Any]] | None,
    exit_state: list[dict[str, Any]] | None,
    *,
    target: str,
    rule_index: int | float | None,
    enabled: bool,
    group: str,
    group_operator: str,
    left_name: str,
    left_params: str,
    operator: str,
    right_name: str,
    right_params: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    entry_rules = _rules_from_state(entry_state)
    exit_rules = _rules_from_state(exit_state)
    selected = entry_rules if target == "入场" else exit_rules
    rule = StrategyRule.create(
        group=str(group or "").strip(),
        group_operator=str(group_operator).upper(),
        left=parse_operand(left_name, left_params),
        operator=operator,
        right=parse_operand(right_name, right_params),
        enabled=enabled,
    )
    if not rule.group:
        raise StrategyValidationError("分组名称不能为空。")

    index = int(rule_index) if rule_index not in (None, "", 0) else None
    if index is None:
        selected.append(rule)
        message = f"已添加{target}规则。"
    else:
        if not 1 <= index <= len(selected):
            raise StrategyValidationError(f"{target}规则序号超出范围。")
        rule.rule_id = selected[index - 1].rule_id
        selected[index - 1] = rule
        message = f"已更新{target}规则第 {index} 条。"
    return _rules_to_state(entry_rules), _rules_to_state(exit_rules), message


def remove_rule(
    entry_state: list[dict[str, Any]] | None,
    exit_state: list[dict[str, Any]] | None,
    *,
    target: str,
    rule_index: int | float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    entry_rules = _rules_from_state(entry_state)
    exit_rules = _rules_from_state(exit_state)
    selected = entry_rules if target == "入场" else exit_rules
    if rule_index in (None, "", 0):
        raise StrategyValidationError("请输入要删除的规则序号。")
    index = int(rule_index)
    if not 1 <= index <= len(selected):
        raise StrategyValidationError(f"{target}规则序号超出范围。")
    selected.pop(index - 1)
    return _rules_to_state(entry_rules), _rules_to_state(exit_rules), f"已删除{target}规则第 {index} 条。"


def move_rule(
    entry_state: list[dict[str, Any]] | None,
    exit_state: list[dict[str, Any]] | None,
    *,
    target: str,
    rule_index: int | float | None,
    direction: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, str]:
    entry_rules = _rules_from_state(entry_state)
    exit_rules = _rules_from_state(exit_state)
    selected = entry_rules if target == "入场" else exit_rules
    if rule_index in (None, "", 0):
        raise StrategyValidationError("请输入要移动的规则序号。")
    index = int(rule_index) - 1
    destination = index + direction
    if not 0 <= index < len(selected) or not 0 <= destination < len(selected):
        raise StrategyValidationError("规则已经位于可移动范围的边界。")
    selected[index], selected[destination] = selected[destination], selected[index]
    new_index = destination + 1
    return (
        _rules_to_state(entry_rules),
        _rules_to_state(exit_rules),
        new_index,
        f"已移动{target}规则。",
    )


def _choices(strategies: list[TradingStrategy]) -> list[tuple[str, str]]:
    return [(f"{'[预置] ' if item.is_builtin else ''}{item.name}", item.strategy_id) for item in strategies]


def _strategy_form(strategy: TradingStrategy) -> tuple[Any, ...]:
    entry_state = _rules_to_state(strategy.entry_rule.rules)
    exit_state = _rules_to_state(strategy.exit_rule.rules)
    initial = strategy.risk_rules.get("initial_atr_stop", {})
    trailing = strategy.risk_rules.get("trailing_atr_stop", {})
    return (
        strategy.strategy_id,
        strategy.created_at,
        strategy.is_builtin,
        strategy.name,
        strategy.description,
        strategy.asset_type,
        strategy.enabled,
        strategy.entry_rule.operator,
        strategy.exit_rule.operator,
        bool(initial.get("enabled", False)),
        int(initial.get("period", 14)),
        float(initial.get("multiple", 2.0)),
        bool(trailing.get("enabled", False)),
        int(trailing.get("period", 14)),
        float(trailing.get("multiple", 3.0)),
        entry_state,
        exit_state,
        build_rule_table(entry_state),
        build_rule_table(exit_state),
    )


def _blank_strategy() -> TradingStrategy:
    return TradingStrategy.new(name="新策略")


def build_strategy_management_tab(service: StrategyManagementService) -> None:
    strategies = service.list_strategies()
    initial = strategies[0] if strategies else _blank_strategy()
    initial_form = _strategy_form(initial)

    with gr.Tab("交易策略"):
        gr.Markdown(
            """
## 技术指标策略管理

通过结构化条件自由组合入场和退出规则。策略保存为本地 JSON，当前迭代只负责策略定义与管理，**不执行回测**。
预置策略为只读，请复制后修改。指标参数使用 JSON，例如 `{"field":"close","period":20}`。
"""
        )
        strategy_id_state = gr.State(initial_form[0])
        created_at_state = gr.State(initial_form[1])
        builtin_state = gr.State(initial_form[2])
        entry_rules_state = gr.State(initial_form[15])
        exit_rules_state = gr.State(initial_form[16])

        strategy_table = gr.Dataframe(
            value=build_strategy_table(strategies),
            headers=STRATEGY_TABLE_COLUMNS,
            label="策略列表",
            interactive=False,
        )
        with gr.Row():
            strategy_selector = gr.Dropdown(
                choices=_choices(strategies),
                value=initial.strategy_id if strategies else None,
                label="已保存策略",
                scale=3,
            )
            load_button = gr.Button("加载")
            refresh_button = gr.Button("刷新")
            new_button = gr.Button("新建")
            copy_button = gr.Button("复制")
            delete_confirm = gr.Checkbox(label="确认删除", value=False)
            delete_button = gr.Button("删除", variant="stop")

        with gr.Row():
            name_input = gr.Textbox(label="策略名称", value=initial_form[3], scale=2)
            asset_type_input = gr.Dropdown(
                choices=["通用", "ETF", "股票"],
                value=initial_form[5],
                label="资产类型",
            )
            enabled_input = gr.Checkbox(label="启用", value=initial_form[6])
        description_input = gr.Textbox(
            label="策略说明",
            value=initial_form[4],
            lines=2,
        )
        with gr.Row():
            gr.Textbox(label="交易方向", value="仅做多", interactive=False)
            gr.Textbox(label="交易周期", value="日线", interactive=False)
            gr.Textbox(label="执行方式", value="下一交易日开盘", interactive=False)

        with gr.Row():
            entry_outer_input = gr.Dropdown(
                choices=["AND", "OR"],
                value=initial_form[7],
                label="入场分组之间",
            )
            exit_outer_input = gr.Dropdown(
                choices=["AND", "OR"],
                value=initial_form[8],
                label="退出分组之间",
            )

        with gr.Tabs():
            with gr.Tab("入场规则"):
                entry_table = gr.Dataframe(
                    value=initial_form[17],
                    headers=RULE_TABLE_COLUMNS,
                    label="入场规则",
                    interactive=False,
                )
            with gr.Tab("退出规则"):
                exit_table = gr.Dataframe(
                    value=initial_form[18],
                    headers=RULE_TABLE_COLUMNS,
                    label="退出规则",
                    interactive=False,
                )

        with gr.Accordion("规则构建器", open=True):
            with gr.Row():
                target_input = gr.Dropdown(choices=["入场", "退出"], value="入场", label="规则类型")
                rule_index_input = gr.Number(label="编辑/删除序号（新增留空）", precision=0)
                rule_enabled_input = gr.Checkbox(label="启用规则", value=True)
                group_input = gr.Textbox(label="分组名称", value="默认组")
                group_operator_input = gr.Dropdown(choices=["AND", "OR"], value="AND", label="组内逻辑")
            with gr.Row():
                left_name_input = gr.Dropdown(choices=OPERAND_CHOICES, value="close", label="左操作数")
                left_params_input = gr.Textbox(label="左参数 JSON", value="{}")
                operator_input = gr.Dropdown(choices=COMPARISON_CHOICES, value=">", label="比较符")
                right_name_input = gr.Dropdown(choices=OPERAND_CHOICES, value="SMA", label="右操作数")
                right_params_input = gr.Textbox(label="右参数 JSON", value='{"field":"close","period":20}')
            with gr.Row():
                add_update_rule_button = gr.Button("添加 / 更新规则", variant="primary")
                remove_rule_button = gr.Button("删除规则")
                move_up_button = gr.Button("上移")
                move_down_button = gr.Button("下移")

        with gr.Accordion("ATR 风控配置", open=False):
            with gr.Row():
                initial_enabled = gr.Checkbox(label="启用初始 ATR 止损", value=initial_form[9])
                initial_period = gr.Number(label="初始止损 ATR 周期", value=initial_form[10], precision=0)
                initial_multiple = gr.Number(label="初始止损倍数", value=initial_form[11])
            with gr.Row():
                trailing_enabled = gr.Checkbox(label="启用 ATR 移动止损", value=initial_form[12])
                trailing_period = gr.Number(label="移动止损 ATR 周期", value=initial_form[13], precision=0)
                trailing_multiple = gr.Number(label="移动止损倍数", value=initial_form[14])

        with gr.Row():
            save_button = gr.Button("保存策略", variant="primary")
            toggle_button = gr.Button("启用 / 停用")
            export_button = gr.Button("导出 JSON")
            import_file = gr.File(label="导入 JSON", file_types=[".json"], type="filepath")
            import_button = gr.Button("导入")
        status_output = gr.Markdown("策略管理已就绪。")
        export_output = gr.File(label="导出的策略 JSON", interactive=False)

        form_outputs = [
            strategy_id_state,
            created_at_state,
            builtin_state,
            name_input,
            description_input,
            asset_type_input,
            enabled_input,
            entry_outer_input,
            exit_outer_input,
            initial_enabled,
            initial_period,
            initial_multiple,
            trailing_enabled,
            trailing_period,
            trailing_multiple,
            entry_rules_state,
            exit_rules_state,
            entry_table,
            exit_table,
        ]

        def refresh_view(selected_id: str | None = None):
            items = service.list_strategies()
            value = selected_id if selected_id and any(item.strategy_id == selected_id for item in items) else (items[0].strategy_id if items else None)
            return gr.update(choices=_choices(items), value=value), build_strategy_table(items)

        def load_strategy(strategy_id: str):
            if not strategy_id:
                raise gr.Error("请先选择策略。")
            strategy = service.get_strategy(strategy_id)
            return (*_strategy_form(strategy), f"### 已加载\n\n{strategy.name}")

        def new_strategy():
            strategy = service.new_strategy()
            return (*_strategy_form(strategy), "### 新建策略\n\n请添加至少一条启用的入场规则后保存。")

        def save_strategy(
            strategy_id: str,
            created_at: str,
            is_builtin: bool,
            name: str,
            description: str,
            asset_type: str,
            enabled: bool,
            entry_outer: str,
            exit_outer: str,
            initial_stop_enabled: bool,
            initial_stop_period: int | float,
            initial_stop_multiple: int | float,
            trailing_stop_enabled: bool,
            trailing_stop_period: int | float,
            trailing_stop_multiple: int | float,
            entry_state,
            exit_state,
        ):
            try:
                strategy = TradingStrategy(
                    strategy_id=strategy_id,
                    name=name,
                    description=description,
                    asset_type=asset_type,
                    enabled=enabled,
                    entry_rule=RuleSet(operator=entry_outer, rules=_rules_from_state(entry_state)),
                    exit_rule=RuleSet(operator=exit_outer, rules=_rules_from_state(exit_state)),
                    risk_rules={
                        "initial_atr_stop": {
                            "enabled": initial_stop_enabled,
                            "period": int(initial_stop_period),
                            "multiple": float(initial_stop_multiple),
                        },
                        "trailing_atr_stop": {
                            "enabled": trailing_stop_enabled,
                            "period": int(trailing_stop_period),
                            "multiple": float(trailing_stop_multiple),
                        },
                    },
                    is_builtin=is_builtin,
                    created_at=created_at,
                )
                saved = service.save_strategy(strategy)
                selector_update, table = refresh_view(saved.strategy_id)
                return saved.strategy_id, saved.created_at, saved.is_builtin, saved.name, selector_update, table, f"### 保存成功\n\n策略名称：**{saved.name}**"
            except StrategyError as exc:
                return strategy_id, created_at, is_builtin, name, gr.update(), build_strategy_table(service.list_strategies()), f"### 保存失败\n\n{exc}"

        def copy_strategy(strategy_id: str):
            try:
                copied = service.copy_strategy(strategy_id)
                selector_update, table = refresh_view(copied.strategy_id)
                return (*_strategy_form(copied), selector_update, table, f"### 复制成功\n\n{copied.name}")
            except StrategyError as exc:
                raise gr.Error(str(exc))

        def delete_strategy(strategy_id: str, confirmed: bool):
            if not confirmed:
                raise gr.Error("请先勾选“确认删除”。")
            service.delete_strategy(strategy_id)
            items = service.list_strategies()
            next_strategy = items[0] if items else _blank_strategy()
            return (*_strategy_form(next_strategy), gr.update(choices=_choices(items), value=next_strategy.strategy_id if items else None), build_strategy_table(items), False, "### 删除成功")

        def toggle_strategy(strategy_id: str):
            toggled = service.toggle_strategy(strategy_id)
            selector_update, table = refresh_view(toggled.strategy_id)
            return toggled.enabled, selector_update, table, f"### 状态已更新\n\n当前：{'启用' if toggled.enabled else '停用'}"

        def import_strategy(path: str | None):
            if not path:
                raise gr.Error("请选择 JSON 文件。")
            imported = service.import_strategy(path)
            selector_update, table = refresh_view(imported.strategy_id)
            return (*_strategy_form(imported), selector_update, table, f"### 导入成功\n\n{imported.name}")

        def export_strategy(strategy_id: str):
            try:
                path = service.export_strategy(strategy_id, Path("strategy_exports"))
                return str(path), f"### 导出成功\n\n`{path.name}`"
            except StrategyError as exc:
                return None, f"### 导出失败\n\n{exc}"

        def handle_add_update(*args):
            try:
                entry, exit_, message = append_or_update_rule(
                    args[0], args[1],
                    target=args[2], rule_index=args[3], enabled=args[4],
                    group=args[5], group_operator=args[6], left_name=args[7],
                    left_params=args[8], operator=args[9], right_name=args[10],
                    right_params=args[11],
                )
                return entry, exit_, build_rule_table(entry), build_rule_table(exit_), f"### 规则已更新\n\n{message}"
            except StrategyError as exc:
                return args[0], args[1], build_rule_table(args[0]), build_rule_table(args[1]), f"### 规则修改失败\n\n{exc}"

        def handle_remove(entry, exit_, target, index):
            try:
                entry, exit_, message = remove_rule(entry, exit_, target=target, rule_index=index)
                return entry, exit_, build_rule_table(entry), build_rule_table(exit_), None, f"### 规则已更新\n\n{message}"
            except StrategyError as exc:
                return entry, exit_, build_rule_table(entry), build_rule_table(exit_), index, f"### 删除失败\n\n{exc}"

        def handle_move(entry, exit_, target, index, direction):
            try:
                entry, exit_, new_index, message = move_rule(entry, exit_, target=target, rule_index=index, direction=direction)
                return entry, exit_, build_rule_table(entry), build_rule_table(exit_), new_index, f"### 规则已更新\n\n{message}"
            except StrategyError as exc:
                return entry, exit_, build_rule_table(entry), build_rule_table(exit_), index, f"### 移动失败\n\n{exc}"

        load_button.click(
            fn=load_strategy,
            inputs=[strategy_selector],
            outputs=form_outputs + [status_output],
            api_name="load_strategy",
        )
        new_button.click(fn=new_strategy, outputs=form_outputs + [status_output], api_name="new_strategy")
        refresh_button.click(fn=refresh_view, inputs=[strategy_selector], outputs=[strategy_selector, strategy_table], api_name="refresh_strategies")

        add_update_rule_button.click(
            fn=handle_add_update,
            inputs=[
                entry_rules_state, exit_rules_state, target_input, rule_index_input,
                rule_enabled_input, group_input, group_operator_input,
                left_name_input, left_params_input, operator_input,
                right_name_input, right_params_input,
            ],
            outputs=[entry_rules_state, exit_rules_state, entry_table, exit_table, status_output],
            api_name="add_or_update_strategy_rule",
        )
        remove_rule_button.click(
            fn=handle_remove,
            inputs=[entry_rules_state, exit_rules_state, target_input, rule_index_input],
            outputs=[entry_rules_state, exit_rules_state, entry_table, exit_table, rule_index_input, status_output],
            api_name="remove_strategy_rule",
        )
        move_up_button.click(
            fn=lambda entry, exit_, target, index: handle_move(entry, exit_, target, index, -1),
            inputs=[entry_rules_state, exit_rules_state, target_input, rule_index_input],
            outputs=[entry_rules_state, exit_rules_state, entry_table, exit_table, rule_index_input, status_output],
            api_name="move_strategy_rule_up",
        )
        move_down_button.click(
            fn=lambda entry, exit_, target, index: handle_move(entry, exit_, target, index, 1),
            inputs=[entry_rules_state, exit_rules_state, target_input, rule_index_input],
            outputs=[entry_rules_state, exit_rules_state, entry_table, exit_table, rule_index_input, status_output],
            api_name="move_strategy_rule_down",
        )

        save_button.click(
            fn=save_strategy,
            inputs=[
                strategy_id_state, created_at_state, builtin_state, name_input,
                description_input, asset_type_input, enabled_input,
                entry_outer_input, exit_outer_input,
                initial_enabled, initial_period, initial_multiple,
                trailing_enabled, trailing_period, trailing_multiple,
                entry_rules_state, exit_rules_state,
            ],
            outputs=[strategy_id_state, created_at_state, builtin_state, name_input, strategy_selector, strategy_table, status_output],
            api_name="save_strategy",
        )
        copy_button.click(
            fn=copy_strategy,
            inputs=[strategy_selector],
            outputs=form_outputs + [strategy_selector, strategy_table, status_output],
            api_name="copy_strategy",
        )
        delete_button.click(
            fn=delete_strategy,
            inputs=[strategy_selector, delete_confirm],
            outputs=form_outputs + [strategy_selector, strategy_table, delete_confirm, status_output],
            api_name="delete_strategy",
        )
        toggle_button.click(
            fn=toggle_strategy,
            inputs=[strategy_selector],
            outputs=[enabled_input, strategy_selector, strategy_table, status_output],
            api_name="toggle_strategy",
        )
        import_button.click(
            fn=import_strategy,
            inputs=[import_file],
            outputs=form_outputs + [strategy_selector, strategy_table, status_output],
            api_name="import_strategy",
        )
        export_button.click(
            fn=export_strategy,
            inputs=[strategy_selector],
            outputs=[export_output, status_output],
            api_name="export_strategy",
        )
