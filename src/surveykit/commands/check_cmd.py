"""check 命令组 - 检查数据质量"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from ..models import CheckResult, ProcessLog
from ..utils import generate_id
from ..workspace import Workspace


@click.group('check')
@click.pass_context
def check_group(ctx):
    """检查数据质量：缺失题目、选项越界、重复受访者"""
    pass


def load_surveys(ws: Workspace, survey_ids: List[str] = None):
    """加载问卷数据"""
    all_surveys = ws.list_surveys()
    
    if survey_ids:
        surveys = []
        for sid in survey_ids:
            survey = ws.get_survey(sid)
            if survey:
                surveys.append(survey)
            else:
                click.echo(f"  ⚠ 未找到问卷: {sid}")
        return surveys
    else:
        return [ws.get_survey(s['name']) for s in all_surveys if ws.get_survey(s['name'])]


@check_group.command('missing')
@click.argument('surveys', nargs=-1, required=False)
@click.option('--threshold', '-t', type=float, default=0.0, help='缺失率阈值 (0-1)')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出报告路径')
@click.option('--show-rows', is_flag=True, help='显示缺失的行号')
@click.pass_context
def check_missing(ctx, surveys: tuple, threshold: float, output: Path, show_rows: bool):
    """检查缺失题目/字段
    
    SURVEYS: 要检查的问卷ID，不指定则检查全部
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey_list = load_surveys(ws, list(surveys) if surveys else None)
    
    if not survey_list:
        click.echo("没有可检查的问卷")
        return
    
    results = []
    all_issues = []
    
    for survey in survey_list:
        click.echo(f"\n检查问卷: {survey.name}")
        
        df = survey.df
        missing_stats = df.isnull().sum()
        missing_pct = df.isnull().mean()
        
        issues = []
        has_missing = False
        for col in df.columns:
            count = missing_stats[col]
            pct = missing_pct[col]
            if pct > 0 and pct >= threshold:
                missing_rows = [i + 2 for i in range(len(df)) if pd.isna(df[col].iloc[i])]
                issues.append({
                    'column': col,
                    'missing_count': int(count),
                    'missing_rate': round(pct, 4),
                    'missing_rows': missing_rows[:20],
                    'total_missing_rows': len(missing_rows),
                })
                click.echo(f"  ⚠ {col}: {count} 缺失 ({pct:.1%})")
                if show_rows:
                    click.echo(f"     行号: {', '.join(map(str, missing_rows[:20]))}{'...' if len(missing_rows) > 20 else ''}")
                has_missing = True
        
        if not has_missing:
            click.echo("  ✓ 全部通过，无缺失数据")
        
        result = CheckResult(
            check_type='missing',
            passed=not has_missing,
            issues=issues,
            summary=f"{survey.name}: {len(issues)} 个字段有缺失",
        )
        results.append(result)
        all_issues.extend([{'survey': survey.name, **i} for i in issues])
    
    if output and not preview:
        import json
        report = {
            'check_type': 'missing',
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'surveys': [s.name for s in survey_list],
            'total_columns': sum(len(s.df.columns) for s in survey_list),
            'total_columns_with_issues': len(all_issues),
            'issues': all_issues,
        }
        
        out_path = output or ws.get_report_path('missing_check.json')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if str(out_path).endswith(('.xlsx', '.xls')):
            pd.DataFrame(all_issues).to_excel(out_path, index=False)
        else:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        click.echo(f"\n报告已保存: {out_path}")


@check_group.command('options')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='要检查的列名')
@click.option('--valid', '-v', required=True, help='有效的选项值，用逗号分隔')
@click.pass_context
def check_options(ctx, survey_id: str, column: str, valid: str):
    """检查选项越界
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    if column not in df.columns:
        click.echo(f"列不存在: {column}")
        click.echo(f"可用列: {', '.join(df.columns)}")
        return
    
    valid_values = [v.strip() for v in valid.split(',')]
    valid_values_str = set(valid_values)
    valid_values_num = set()
    for v in valid_values:
        try:
            valid_values_num.add(float(v))
        except ValueError:
            pass
    
    issues = []
    for idx, val in enumerate(df[column]):
        val_str = str(val).strip()
        val_num = None
        try:
            val_num = float(val)
        except (ValueError, TypeError):
            pass
        
        is_valid = (val_str in valid_values_str) or (val_num is not None and val_num in valid_values_num)
        if pd.notna(val) and not is_valid:
            issues.append({
                'row': idx + 2,
                'value': val_str,
            })
            click.echo(f"  ⚠ 第 {idx + 2} 行: {val_str} (有效选项: {valid})")
    
    if not issues:
        click.echo("  ✓ 所有选项均有效")
    else:
        click.echo(f"\n共发现 {len(issues)} 个越界选项")


@check_group.command('duplicate')
@click.argument('survey_id')
@click.option('--columns', '-c', default=None, help='用于查重的列名，逗号分隔 (默认: 全部列)')
@click.option('--keep', type=click.Choice(['first', 'last', False]), default='first', help='保留策略')
@click.pass_context
def check_duplicate(ctx, survey_id: str, columns: str, keep: str):
    """检查重复受访者
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    
    subset = [c.strip() for c in columns.split(',')] if columns else None
    if subset:
        invalid_cols = [c for c in subset if c not in df.columns]
        if invalid_cols:
            click.echo(f"列不存在: {', '.join(invalid_cols)}")
            return
    
    dup_mask = df.duplicated(subset=subset, keep=keep)
    duplicates = df[dup_mask]
    
    if duplicates.empty:
        click.echo("  ✓ 未发现重复记录")
        return
    
    click.echo(f"发现 {len(duplicates)} 条重复记录:")
    for idx, row in duplicates.iterrows():
        if subset:
            values = {c: row[c] for c in subset}
        else:
            values = row.to_dict()
        click.echo(f"  ⚠ 第 {idx + 2} 行: {values}")


@check_group.command('template')
@click.argument('survey_id')
@click.argument('template_path', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='异常清单输出路径')
@click.option('--summary', is_flag=True, help='仅显示统计摘要')
@click.pass_context
def check_template(ctx, survey_id: str, template_path: Path, output: Path, summary: bool):
    """按模板一次性检查：缺列、必填缺失、选项越界、数值范围、类型不匹配
    
    SURVEY_ID: 问卷ID
    TEMPLATE_PATH: 模板文件路径 (JSON/CSV)
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    from ..template import load_template, validate_with_template
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    try:
        template = load_template(template_path)
    except Exception as e:
        click.echo(f"加载模板失败: {e}")
        return
    
    click.echo(f"问卷: {survey.name} ({len(survey.df)} 行)")
    click.echo(f"模板: {template.name} (v{template.version}, {len(template.variables)} 个变量)")
    click.echo()
    
    issues, issues_df = validate_with_template(survey.df, template)
    
    if not issues:
        click.echo("✅ 全部通过！未发现异常")
        return
    
    error_count = len([i for i in issues if i['severity'] == 'error'])
    warning_count = len([i for i in issues if i['severity'] == 'warning'])
    info_count = len([i for i in issues if i['severity'] == 'info'])
    
    click.echo(f"发现异常总计: {len(issues)}")
    click.echo(f"  错误 (Error): {error_count}")
    click.echo(f"  警告 (Warning): {warning_count}")
    click.echo(f"  信息 (Info): {info_count}")
    click.echo()
    
    if not summary:
        type_groups = {}
        for issue in issues:
            t = issue['type']
            if t not in type_groups:
                type_groups[t] = []
            type_groups[t].append(issue)
        
        for issue_type, type_issues in type_groups.items():
            click.echo(f"--- {issue_type} ({len(type_issues)} 项) ---")
            for issue in type_issues[:10]:
                row_info = f"第{issue['row']}行" if issue['row'] else "全局"
                val_info = f" 值: {issue['value']}" if issue['value'] else ""
                click.echo(f"  [{issue['severity'].upper()}] {issue['column']} ({row_info}): {issue['message']}{val_info}")
            if len(type_issues) > 10:
                click.echo(f"  ... 还有 {len(type_issues) - 10} 项")
            click.echo()
    
    if output and not preview:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if str(out_path).endswith(('.xlsx', '.xls')):
            issues_df.to_excel(out_path, index=False)
        else:
            issues_df.to_csv(out_path, index=False, encoding='utf-8-sig')
        
        click.echo(f"异常清单已保存: {out_path}")


@check_group.command('all')
@click.argument('surveys', nargs=-1, required=False)
@click.option('--template', '-t', type=click.Path(exists=True, path_type=Path), default=None, help='使用模板文件')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出报告路径')
@click.pass_context
def check_all(ctx, surveys: tuple, template: Path, output: Path):
    """运行所有检查
    
    SURVEYS: 要检查的问卷ID，不指定则检查全部
    """
    click.echo("=== 运行全部检查 ===")
    
    click.echo("\n--- 缺失检查 ---")
    ctx.invoke(check_missing, surveys=surveys, threshold=0.0, output=None, show_rows=False)
    
    if template:
        click.echo("\n--- 模板综合检查 ---")
        from .check_cmd import load_surveys
        survey_list = load_surveys(ctx.obj['workspace'], list(surveys) if surveys else None)
        for survey in survey_list:
            ctx.invoke(check_template, survey_id=survey.name, template_path=template, output=None, summary=True)
    
    click.echo("\n=== 检查完成 ===")
