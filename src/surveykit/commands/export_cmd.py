"""export 命令组 - 导出可交付文件、保留处理日志"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

from ..models import ProcessLog
from ..workspace import Workspace


@click.group('export')
@click.pass_context
def export_group(ctx):
    """导出可交付文件、保留处理日志"""
    pass


@export_group.command('survey')
@click.argument('survey_id')
@click.option('--output', '-o', type=click.Path(path_type=Path), required=True, help='输出文件路径')
@click.option('--format', '-f', type=click.Choice(['xlsx', 'csv', 'json', 'parquet']), default='xlsx', help='输出格式')
@click.option('--columns', '-c', default=None, help='指定导出列，逗号分隔')
@click.option('--encoding', '-e', default='utf-8-sig', help='CSV编码')
@click.pass_context
def export_survey(ctx, survey_id: str, output: Path, format: str, columns: str, encoding: str):
    """导出问卷数据
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    
    if columns:
        cols = [c.strip() for c in columns.split(',')]
        cols = [c for c in cols if c in df.columns]
        if cols:
            df = df[cols]
        else:
            click.echo(f"  ⚠ 指定的列都不存在，导出全部列")
    
    output = Path(output)
    if not output.suffix:
        output = output.with_suffix(f'.{format}')
    
    click.echo(f"导出问卷: {survey_id} ({len(df)} 行, {len(df.columns)} 列)")
    click.echo(f"  输出: {output}")
    click.echo(f"  格式: {format}")
    
    if not preview:
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'xlsx':
            df.to_excel(output, index=False)
        elif format == 'csv':
            df.to_csv(output, index=False, encoding=encoding)
        elif format == 'json':
            df.to_json(output, orient='records', force_ascii=False, indent=2)
        elif format == 'parquet':
            df.to_parquet(output, index=False)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='export survey',
            params={'survey': survey_id, 'format': format, 'columns': columns},
            input_files=[str(survey.source_path)],
            output_files=[str(output)],
            changes=[f"导出问卷: {survey_id} -> {output}"],
        )
        ws.add_log(log)
        click.echo(f"\n导出完成{' (预览模式，未保存)' if preview else ''}")
    else:
        click.echo(f"\n预览模式，未实际导出")


@export_group.command('interview')
@click.argument('interview_id')
@click.option('--output', '-o', type=click.Path(path_type=Path), required=True, help='输出文件路径')
@click.pass_context
def export_interview(ctx, interview_id: str, output: Path):
    """导出访谈文本
    
    INTERVIEW_ID: 访谈ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    interview = ws.get_interview(interview_id)
    if not interview:
        click.echo(f"未找到访谈: {interview_id}")
        return
    
    output = Path(output)
    click.echo(f"导出访谈: {interview_id}")
    click.echo(f"  输出: {output}")
    
    if not preview:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', encoding='utf-8') as f:
            f.write(interview.content)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='export interview',
            params={'interview': interview_id},
            input_files=[str(interview.source_path)],
            output_files=[str(output)],
            changes=[f"导出访谈: {interview_id} -> {output}"],
        )
        ws.add_log(log)
        click.echo(f"\n导出完成{' (预览模式，未保存)' if preview else ''}")


@export_group.command('all')
@click.argument('output_dir', type=click.Path(path_type=Path))
@click.option('--format', '-f', type=click.Choice(['xlsx', 'csv']), default='xlsx', help='问卷导出格式')
@click.pass_context
def export_all(ctx, output_dir: Path, format: str):
    """导出所有问卷和访谈
    
    OUTPUT_DIR: 输出目录
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    surveys = ws.list_surveys()
    interviews = ws.list_interviews()
    
    click.echo(f"导出到: {out_dir}")
    click.echo(f"  问卷: {len(surveys)} 个")
    click.echo(f"  访谈: {len(interviews)} 个")
    
    output_files = []
    
    for s in surveys:
        survey = ws.get_survey(s['name'])
        if survey:
            out_path = out_dir / f"{survey.name}.{format}"
            if not preview:
                if format == 'xlsx':
                    survey.df.to_excel(out_path, index=False)
                else:
                    survey.df.to_csv(out_path, index=False, encoding='utf-8-sig')
                output_files.append(str(out_path))
            click.echo(f"  ✓ 问卷: {survey.name}")
    
    interview_dir = out_dir / 'interviews'
    for i in interviews:
        interview = ws.get_interview(i['name'])
        if interview:
            out_path = interview_dir / f"{interview.name}.txt"
            if not preview:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(interview.content)
                output_files.append(str(out_path))
            click.echo(f"  ✓ 访谈: {interview.name}")
    
    if not preview:
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='export all',
            params={'output_dir': str(output_dir), 'format': format},
            input_files=[],
            output_files=output_files,
            changes=[f"批量导出: {len(surveys)} 个问卷, {len(interviews)} 个访谈"],
        )
        ws.add_log(log)
    
    click.echo(f"\n导出完成{' (预览模式，未保存)' if preview else ''}")


@export_group.command('logs')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=None, help='输出文件路径')
@click.option('--limit', '-n', type=int, default=50, help='显示最近N条')
@click.option('--command', '-c', default=None, help='按命令过滤')
@click.option('--survey', '-s', default=None, help='按问卷名称过滤')
@click.option('--start', default=None, help='起始时间 (YYYYMMDD_HHMMSS)')
@click.option('--end', default=None, help='结束时间 (YYYYMMDD_HHMMSS)')
@click.option('--format', '-f', type=click.Choice(['json', 'xlsx', 'csv']), default='json', help='导出格式')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息')
@click.pass_context
def export_logs(ctx, output: Path, limit: int, command: str, survey: str, start: str, end: str, format: str, verbose: bool):
    """查看/导出处理日志
    
    支持按时间范围、命令类型、问卷名称过滤，可导出为表格
    """
    ws: Workspace = ctx.obj['workspace']
    
    log_dir = ws.root / 'logs'
    log_files = sorted(log_dir.glob('*.json'), reverse=True)
    
    logs = []
    for lf in log_files:
        with open(lf, 'r', encoding='utf-8') as f:
            log = json.load(f)
            logs.append(log)
    
    if command:
        logs = [l for l in logs if command.lower() in l.get('command', '').lower()]
    
    if survey:
        logs = [l for l in logs if any(survey.lower() in str(c).lower() for c in l.get('changes', []))]
    
    if start:
        logs = [l for l in logs if l.get('timestamp', '') >= start]
    
    if end:
        logs = [l for l in logs if l.get('timestamp', '') <= end]
    
    logs = logs[:limit]
    
    for log in logs:
        ts = log.get('timestamp', '')
        cmd = log.get('command', '')
        input_rows = log.get('input_row_count', '-')
        output_rows = log.get('output_row_count', '-')
        affected = log.get('affected_rows', '-')
        cols = log.get('modified_columns', [])
        
        if verbose:
            click.echo(f"{'='*50}")
            click.echo(f"时间: {ts}")
            click.echo(f"命令: {cmd}")
            click.echo(f"参数: {log.get('params', {})}")
            if input_rows != '-':
                click.echo(f"输入行数: {input_rows}")
            if output_rows != '-':
                click.echo(f"输出行数: {output_rows}")
            if affected != '-':
                click.echo(f"影响行数: {affected}")
            if cols:
                click.echo(f"修改字段: {', '.join(cols)}")
            click.echo("变更:")
            for change in log.get('changes', []):
                click.echo(f"  - {change}")
            click.echo()
        else:
            cols_str = f" [{', '.join(cols)}]" if cols else ""
            rows_str = f" (输入:{input_rows}→输出:{output_rows})" if input_rows != '-' else ""
            click.echo(f"[{ts}] {cmd}{rows_str}{cols_str}")
            for change in log.get('changes', [])[:2]:
                click.echo(f"  - {change}")
    
    click.echo(f"\n共 {len(logs)} 条日志记录")
    
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if out_path.suffix in ['.xlsx', '.xls']:
            actual_format = 'xlsx'
        elif out_path.suffix == '.csv':
            actual_format = 'csv'
        else:
            actual_format = format
        
        if actual_format == 'json':
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        else:
            import pandas as pd
            rows = []
            for log in logs:
                row = {
                    '时间': log.get('timestamp', ''),
                    '命令': log.get('command', ''),
                    '参数': json.dumps(log.get('params', {}), ensure_ascii=False),
                    '输入行数': log.get('input_row_count', None),
                    '输出行数': log.get('output_row_count', None),
                    '影响行数': log.get('affected_rows', None),
                    '修改字段': ', '.join(log.get('modified_columns', [])),
                    '变更摘要': '; '.join(log.get('changes', [])),
                }
                rows.append(row)
            
            columns = ['时间', '命令', '参数', '输入行数', '输出行数', '影响行数', '修改字段', '变更摘要']
            df = pd.DataFrame(rows, columns=columns)
            
            if actual_format == 'xlsx':
                df.to_excel(out_path, index=False, engine='openpyxl')
            else:
                df.to_csv(out_path, index=False, encoding='utf-8-sig')
        
        status = f"{len(logs)} 条" if len(logs) > 0 else "空"
        click.echo(f"日志已导出到: {out_path} ({status})")
