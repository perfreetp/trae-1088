"""report 命令组 - 统计题目完成率、生成异常清单"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

from ..models import ProcessLog
from ..utils import is_empty
from ..workspace import Workspace
from ..template import load_template, validate_with_template


@click.group('report')
@click.pass_context
def report_group(ctx):
    """统计题目完成率、生成异常清单"""
    pass


@report_group.command('completion')
@click.argument('surveys', nargs=-1, required=False)
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出报告路径')
@click.option('--threshold', '-t', type=float, default=0.9, help='完成率阈值')
@click.pass_context
def report_completion(ctx, surveys: tuple, output: Path, threshold: float):
    """统计题目完成率
    
    SURVEYS: 问卷ID，不指定则全部
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    from .check_cmd import load_surveys
    survey_list = load_surveys(ws, list(surveys) if surveys else None)
    
    if not survey_list:
        click.echo("没有可统计的问卷")
        return
    
    all_results = []
    
    for survey in survey_list:
        click.echo(f"\n问卷: {survey.name} ({survey.row_count} 份)")
        
        df = survey.df
        
        low_completion = []
        click.echo("  各题目完成率:")
        for col in df.columns:
            answered_mask = ~df[col].apply(is_empty)
            answered_count = int(answered_mask.sum())
            rate = answered_count / len(df) if len(df) > 0 else 0
            status = "✓" if rate >= threshold else "⚠"
            click.echo(f"    {status} {col}: {rate:.1%} (已答: {answered_count}/{len(df)})")
            
            all_results.append({
                'survey': survey.name,
                'column': col,
                'completion_rate': round(rate, 4),
                'total_count': len(df),
                'answered_count': answered_count,
                'passed': rate >= threshold,
            })
            
            if rate < threshold:
                low_completion.append({'column': col, 'rate': round(rate, 4)})
        
        full_answer_mask = ~df.apply(lambda row: all(is_empty(v) for v in row), axis=1)
        overall_rate = full_answer_mask.mean() if len(df) > 0 else 0
        click.echo(f"\n  完整答卷率: {overall_rate:.1%}")
    
    if output and not preview:
        report = {
            'report_type': 'completion',
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'surveys': [s.name for s in survey_list],
            'total_columns': len(all_results),
            'low_completion_count': len([r for r in all_results if not r['passed']]),
            'details': all_results,
        }
        
        out_path = Path(output) or ws.get_report_path('completion_report.json')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        if out_path.suffix in ['.xlsx', '.xls']:
            pd.DataFrame(all_results).to_excel(out_path, index=False)
        
        click.echo(f"\n报告已保存: {out_path}")


@report_group.command('anomalies')
@click.argument('survey_id')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出报告路径')
@click.option('--numeric-only', is_flag=True, help='仅检查数值列')
@click.option('--zscore', type=float, default=3.0, help='Z-score阈值')
@click.pass_context
def report_anomalies(ctx, survey_id: str, output: Path, numeric_only: bool, zscore: float):
    """生成异常数据清单
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    anomalies = []
    
    click.echo(f"检查问卷: {survey_id} ({len(df)} 行)")
    
    numeric_cols = df.select_dtypes(include=['number']).columns
    text_cols = df.select_dtypes(include=['object']).columns
    
    for col in numeric_cols:
        mean = df[col].mean()
        std = df[col].std()
        if std == 0 or pd.isna(std):
            continue
        
        for idx, val in enumerate(df[col]):
            if pd.notna(val):
                z = abs((val - mean) / std) if std > 0 else 0
                if z > zscore:
                    anomalies.append({
                        '问卷名': survey.name,
                        '字段': col,
                        '行号': idx + 2,
                        '异常类型': '数值异常(Z-score)',
                        '实际值': val,
                        '说明': f'Z-score={z:.2f}, mean={mean:.2f}, std={std:.2f}',
                    })
    
    if not numeric_only:
        for col in text_cols:
            for idx, val in enumerate(df[col]):
                if pd.notna(val):
                    s = str(val)
                    if len(s) > 500:
                        anomalies.append({
                            '问卷名': survey.name,
                            '字段': col,
                            '行号': idx + 2,
                            '异常类型': '文本过长',
                            '实际值': s[:100] + '...',
                            '说明': f'长度={len(s)}字符',
                        })
    
    dup_mask = df.duplicated(keep=False)
    for idx, is_dup in enumerate(dup_mask):
        if is_dup:
            anomalies.append({
                '问卷名': survey.name,
                '字段': '[全局]',
                '行号': idx + 2,
                '异常类型': '重复行',
                '实际值': '',
                '说明': '与其他行重复',
            })
    
    click.echo(f"\n发现 {len(anomalies)} 个异常:")
    for a in anomalies[:20]:
        click.echo(f"  第{a['行号']}行 [{a['字段']}]: {a['异常类型']} - {a.get('实际值', '')}")
    
    if len(anomalies) > 20:
        click.echo(f"  ... 还有 {len(anomalies) - 20} 条异常")
    elif len(anomalies) == 0:
        click.echo("  无异常数据")
    
    if output and not preview:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if len(anomalies) > 0:
            out_df = pd.DataFrame(anomalies, columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明'])
        else:
            out_df = pd.DataFrame(columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明'])
        
        if out_path.suffix in ['.xlsx', '.xls']:
            out_df.to_excel(out_path, index=False)
        else:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'survey': survey_id,
                    'timestamp': datetime.now().isoformat(),
                    'zscore_threshold': zscore,
                    'total_anomalies': len(anomalies),
                    'anomalies': anomalies,
                }, f, ensure_ascii=False, indent=2)
        
        status = f"{len(anomalies)} 条异常" if len(anomalies) > 0 else "无异常"
        click.echo(f"\n异常清单已保存: {out_path} ({status})")


@report_group.command('summary')
@click.argument('surveys', nargs=-1, required=False)
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出报告路径')
@click.pass_context
def report_summary(ctx, surveys: tuple, output: Path):
    """生成数据汇总报告
    
    SURVEYS: 问卷ID，不指定则全部
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    from .check_cmd import load_surveys
    survey_list = load_surveys(ws, list(surveys) if surveys else None)
    
    if not survey_list:
        click.echo("没有可分析的问卷")
        return
    
    click.echo("=== 数据汇总报告 ===\n")
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_surveys': len(survey_list),
        'surveys': [],
    }
    
    total_rows = 0
    total_columns = 0
    
    for survey in survey_list:
        df = survey.df
        overall_rate = df.notna().all(axis=1).mean()
        
        click.echo(f"问卷: {survey.name}")
        click.echo(f"  样本量: {len(df)}")
        click.echo(f"  题目数: {len(df.columns)}")
        click.echo(f"  完整答卷率: {overall_rate:.1%}")
        click.echo(f"  数值列: {len(df.select_dtypes(include=['number']).columns)}")
        click.echo(f"  文本列: {len(df.select_dtypes(include=['object']).columns)}")
        click.echo()
        
        total_rows += len(df)
        total_columns += len(df.columns)
        
        summary['surveys'].append({
            'name': survey.name,
            'rows': len(df),
            'columns': len(df.columns),
            'overall_completion': round(overall_rate, 4),
            'numeric_columns': len(df.select_dtypes(include=['number']).columns),
            'text_columns': len(df.select_dtypes(include=['object']).columns),
            'column_names': list(df.columns),
        })
    
    click.echo(f"总计: {len(survey_list)} 个问卷, {total_rows} 条记录, {total_columns} 个变量")
    
    summary['total_rows'] = total_rows
    summary['total_columns'] = total_columns
    
    if output and not preview:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        click.echo(f"\n汇总报告已保存: {out_path}")


@report_group.command('quality')
@click.argument('surveys', nargs=-1, required=False)
@click.option('--output', '-o', type=click.Path(path_type=Path), required=True, help='输出报告路径 (.xlsx)')
@click.option('--template', '-t', type=click.Path(exists=True, path_type=Path), default=None, help='模板文件路径')
@click.pass_context
def report_quality(ctx, surveys: tuple, output: Path, template: Path):
    """生成质检汇总报告（多工作表 xlsx）
    
    包含：总览、缺失明细、异常明细、完成率、处理历史
    
    SURVEYS: 问卷ID，不指定则全部
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    from .check_cmd import load_surveys
    survey_list = load_surveys(ws, list(surveys) if surveys else None)
    
    if not survey_list:
        click.echo("没有可分析的问卷")
        return
    
    click.echo("生成质检汇总报告...")
    click.echo(f"  问卷数量: {len(survey_list)}")
    if template:
        click.echo(f"  使用模板: {template}")
    
    if preview:
        click.echo("  预览模式，不生成文件")
        return
    
    all_missing = []
    all_completion = []
    all_anomalies = []
    all_template_issues = []
    
    for survey in survey_list:
        df = survey.df
        
        click.echo(f"  处理问卷: {survey.name} ({len(df)} 行)")
        
        for col in df.columns:
            missing_mask = df[col].apply(is_empty)
            missing_count = int(missing_mask.sum())
            missing_rate = missing_count / len(df) if len(df) > 0 else 0
            
            missing_rows = [i + 2 for i, is_missing in enumerate(missing_mask) if is_missing]
            
            all_missing.append({
                '问卷名': survey.name,
                '字段': col,
                '缺失数量': missing_count,
                '缺失率': round(missing_rate, 4),
                '行号': ', '.join(map(str, missing_rows[:20])) if missing_rows else '',
                '总行数': len(df),
            })
            
            all_completion.append({
                '问卷名': survey.name,
                '字段': col,
                '总题数': len(df),
                '已答题数': len(df) - missing_count,
                '完成率': round(1 - missing_rate, 4),
            })
        
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            mean = df[col].mean()
            std = df[col].std()
            if std == 0 or pd.isna(std):
                continue
            for idx, val in enumerate(df[col]):
                if pd.notna(val):
                    z = abs((val - mean) / std) if std > 0 else 0
                    if z > 3.0:
                        all_anomalies.append({
                            '问卷名': survey.name,
                            '字段': col,
                            '行号': idx + 2,
                            '异常类型': '数值异常(Z-score)',
                            '实际值': val,
                            '说明': f'Z-score={z:.2f}, mean={mean:.2f}, std={std:.2f}',
                        })
        
        dup_mask = df.duplicated(keep=False)
        for idx, is_dup in enumerate(dup_mask):
            if is_dup:
                all_anomalies.append({
                    '问卷名': survey.name,
                    '字段': '[全局]',
                    '行号': idx + 2,
                    '异常类型': '重复行',
                    '实际值': '',
                    '说明': '与其他行重复',
                })
        
        if template:
            tmpl = load_template(template)
            issues, _ = validate_with_template(df, tmpl)
            for issue in issues:
                all_template_issues.append({
                    '问卷名': survey.name,
                    '类型': issue.get('type', ''),
                    '级别': issue.get('severity', ''),
                    '字段': issue.get('column', ''),
                    '行号': issue.get('row', ''),
                    '值': issue.get('value', ''),
                    '说明': issue.get('message', ''),
                })
    
    log_dir = ws.root / 'logs'
    log_files = sorted(log_dir.glob('*.json')) if log_dir.exists() else []
    all_logs = []
    for lf in log_files:
        with open(lf, 'r', encoding='utf-8') as f:
            log = json.load(f)
            all_logs.append({
                '时间': log.get('timestamp', ''),
                '命令': log.get('command', ''),
                '输入行数': log.get('input_row_count', ''),
                '输出行数': log.get('output_row_count', ''),
                '影响行数': log.get('affected_rows', ''),
                '修改字段': ', '.join(log.get('modified_columns', [])),
                '变更摘要': '; '.join(log.get('changes', [])),
            })
    
    total_rows = sum(len(s.df) for s in survey_list)
    total_cols = sum(len(s.df.columns) for s in survey_list)
    total_missing = sum(m['缺失数量'] for m in all_missing)
    total_anomalies = len(all_anomalies) + len(all_template_issues)
    
    overview = pd.DataFrame([{
        '报告生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '问卷数量': len(survey_list),
        '总记录数': total_rows,
        '总字段数': total_cols,
        '缺失值总数': total_missing,
        '异常总数': total_anomalies,
        '处理操作数': len(all_logs),
        '模板验证': '是' if template else '否',
    }])
    
    missing_df = pd.DataFrame(all_missing) if all_missing else pd.DataFrame(columns=['问卷名', '字段', '缺失数量', '缺失率', '行号', '总行数'])
    completion_df = pd.DataFrame(all_completion) if all_completion else pd.DataFrame(columns=['问卷名', '字段', '总题数', '已答题数', '完成率'])
    anomalies_df = pd.DataFrame(all_anomalies, columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明']) if all_anomalies else pd.DataFrame(columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明'])
    template_df = pd.DataFrame(all_template_issues) if all_template_issues else pd.DataFrame(columns=['问卷名', '类型', '级别', '字段', '行号', '值', '说明'])
    logs_df = pd.DataFrame(all_logs) if all_logs else pd.DataFrame(columns=['时间', '命令', '输入行数', '输出行数', '影响行数', '修改字段', '变更摘要'])
    
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        overview.to_excel(writer, sheet_name='总览', index=False)
        missing_df.to_excel(writer, sheet_name='缺失明细', index=False)
        anomalies_df.to_excel(writer, sheet_name='异常明细', index=False)
        if template:
            template_df.to_excel(writer, sheet_name='模板异常', index=False)
        completion_df.to_excel(writer, sheet_name='完成率', index=False)
        logs_df.to_excel(writer, sheet_name='处理历史', index=False)
    
    click.echo(f"\n✅ 质检汇总报告已保存: {out_path}")
    click.echo(f"  工作表: 总览、缺失明细、异常明细、{'模板异常、' if template else ''}完成率、处理历史")
    click.echo(f"  概览: {len(survey_list)} 个问卷, {total_rows} 条记录, {total_missing} 个缺失, {total_anomalies} 个异常")
