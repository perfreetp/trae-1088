"""import 命令组 - 导入表格和文本目录"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime

from ..models import SurveyData, InterviewData, ProcessLog
from ..utils import get_file_list, read_text_file, safe_filename
from ..workspace import Workspace


@click.group('import')
@click.pass_context
def import_group(ctx):
    """导入表格和文本目录"""
    pass


@import_group.command('table')
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--sheet', '-s', default=None, help='Excel工作表名称')
@click.option('--name', '-n', default=None, help='问卷名称 (默认: 文件名)')
@click.option('--round', 'round_num', type=int, default=None, help='问卷轮次')
@click.option('--encoding', '-e', default=None, help='CSV文件编码')
@click.pass_context
def import_table(ctx, path: Path, sheet: str, name: str, round_num: int, encoding: str):
    """导入表格文件 (Excel/CSV)
    
    PATH: 表格文件路径或目录
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    files = []
    if path.is_dir():
        files = get_file_list(path, ['.xlsx', '.xls', '.csv'])
    else:
        files = [path]
    
    if not files:
        click.echo("未找到可导入的表格文件")
        return
    
    imported = []
    changes = []
    
    for f in files:
        try:
            if f.suffix.lower() in ['.xlsx', '.xls']:
                excel_file = pd.ExcelFile(f)
                sheets = [sheet] if sheet else excel_file.sheet_names
                
                for sh in sheets:
                    df = pd.read_excel(f, sheet_name=sh)
                    survey_name = name or f"{f.stem}_{sh}" if len(sheets) > 1 else (name or f.stem)
                    survey_name = safe_filename(survey_name)
                    
                    survey = SurveyData(
                        name=survey_name,
                        df=df,
                        source_path=f,
                        sheet_name=sh,
                        round_num=round_num,
                    )
                    
                    if not preview:
                        ws.add_survey(survey)
                    
                    imported.append(survey_name)
                    changes.append(f"导入表格: {f} -> {survey_name} ({len(df)} 行, {len(df.columns)} 列)")
                    click.echo(f"  ✓ 导入: {survey_name} ({len(df)} 行, {len(df.columns)} 列)")
            else:
                df = pd.read_csv(f, encoding=encoding or 'utf-8')
                survey_name = safe_filename(name or f.stem)
                
                survey = SurveyData(
                    name=survey_name,
                    df=df,
                    source_path=f,
                    round_num=round_num,
                )
                
                if not preview:
                    ws.add_survey(survey)
                
                imported.append(survey_name)
                changes.append(f"导入CSV: {f} -> {survey_name} ({len(df)} 行, {len(df.columns)} 列)")
                click.echo(f"  ✓ 导入: {survey_name} ({len(df)} 行, {len(df.columns)} 列)")
                
        except Exception as e:
            click.echo(f"  ✗ 导入失败 {f}: {e}")
    
    if not preview and imported:
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='import table',
            params={'path': str(path), 'sheet': sheet, 'round': round_num},
            input_files=[str(f) for f in files],
            output_files=[],
            changes=changes,
        )
        ws.add_log(log)
    
    click.echo(f"\n共导入 {len(imported)} 个问卷{' (预览模式，未保存)' if preview else ''}")


@import_group.command('interview')
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--name', '-n', default=None, help='访谈名称前缀')
@click.option('--pattern', default='*.txt', help='文件名匹配模式')
@click.pass_context
def import_interview(ctx, path: Path, name: str, pattern: str):
    """导入访谈文本目录
    
    PATH: 访谈文本文件或目录
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    files = []
    if path.is_dir():
        files = [f for f in path.rglob(pattern) if f.is_file()]
    else:
        files = [path]
    
    if not files:
        click.echo("未找到可导入的访谈文件")
        return
    
    imported = []
    changes = []
    
    for f in files:
        try:
            content = read_text_file(f)
            interview_name = safe_filename(f"{name}_{f.stem}" if name else f.stem)
            
            interview = InterviewData(
                name=interview_name,
                content=content,
                source_path=f,
            )
            
            if not preview:
                ws.add_interview(interview)
            
            imported.append(interview_name)
            changes.append(f"导入访谈: {f} -> {interview_name}")
            click.echo(f"  ✓ 导入: {interview_name} ({len(content)} 字符)")
            
        except Exception as e:
            click.echo(f"  ✗ 导入失败 {f}: {e}")
    
    if not preview and imported:
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='import interview',
            params={'path': str(path), 'pattern': pattern},
            input_files=[str(f) for f in files],
            output_files=[],
            changes=changes,
        )
        ws.add_log(log)
    
    click.echo(f"\n共导入 {len(imported)} 个访谈{' (预览模式，未保存)' if preview else ''}")


@import_group.command('dir')
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--round', 'round_num', type=int, default=None, help='问卷轮次')
@click.pass_context
def import_dir(ctx, directory: Path, round_num: int):
    """批量导入目录下所有表格和文本
    
    DIRECTORY: 数据目录路径
    """
    ws: Workspace = ctx.obj['workspace']
    
    click.echo(f"导入目录: {directory}")
    click.echo("--- 表格 ---")
    ctx.invoke(import_table, path=directory, sheet=None, name=None, round_num=round_num, encoding=None)
    
    click.echo("\n--- 访谈 ---")
    ctx.invoke(import_interview, path=directory, name=None, pattern='*.txt')
