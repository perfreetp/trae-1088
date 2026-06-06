"""clean 命令组 - 数据清洗"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import shutil

from ..models import ProcessLog, SurveyData
from ..utils import normalize_date, normalize_region, get_file_list, safe_filename
from ..workspace import Workspace


@click.group('clean')
@click.pass_context
def clean_group(ctx):
    """数据清洗：统一日期和地区写法、批量重命名附件"""
    pass


@clean_group.command('date')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='日期列名')
@click.option('--new-column', '-n', default=None, help='新列名 (默认覆盖原列)')
@click.pass_context
def clean_date(ctx, survey_id: str, column: str, new_column: str):
    """统一日期格式为 YYYY-MM-DD
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df.copy()
    if column not in df.columns:
        click.echo(f"列不存在: {column}")
        click.echo(f"可用列: {', '.join(df.columns)}")
        return
    
    target_col = new_column or column
    input_rows = len(df)
    changes = []
    
    click.echo(f"转换日期列: {column} -> {target_col}")
    
    before = df[column].copy()
    df[target_col] = df[column].apply(lambda x: normalize_date(x))
    changed_mask = before.astype(str) != df[target_col].astype(str)
    changed_count = int(changed_mask.sum())
    
    click.echo(f"  共处理 {input_rows} 条记录, 影响 {changed_count} 行")
    
    sample_before = before.head(5).tolist()
    sample_after = df[target_col].head(5).tolist()
    click.echo("  示例:")
    for b, a in zip(sample_before, sample_after):
        click.echo(f"    {b} -> {a}")
    
    if not preview:
        new_survey = SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            sheet_name=survey.sheet_name,
            metadata=survey.metadata,
            round_num=survey.round_num,
        )
        ws.add_survey(new_survey)
        changes.append(f"统一日期格式: {column} -> {target_col}, 影响 {changed_count} 行")
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='clean date',
            params={'survey': survey_id, 'column': column, 'new_column': new_column},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=changes,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[target_col],
            affected_rows=changed_count,
        )
        ws.add_log(log)
        click.echo(f"\n已更新问卷: {survey.name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@clean_group.command('region')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='地区列名')
@click.option('--new-column', '-n', default=None, help='新列名 (默认覆盖原列)')
@click.option('--map-file', '-m', type=click.Path(exists=True, path_type=Path), default=None, help='自定义地区映射JSON文件')
@click.pass_context
def clean_region(ctx, survey_id: str, column: str, new_column: str, map_file: Path):
    """统一地区名称写法
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df.copy()
    if column not in df.columns:
        click.echo(f"列不存在: {column}")
        return
    
    import json
    region_map = {}
    if map_file:
        with open(map_file, 'r', encoding='utf-8') as f:
            region_map = json.load(f)
    
    target_col = new_column or column
    input_rows = len(df)
    changes = []
    
    click.echo(f"标准化地区列: {column} -> {target_col}")
    
    before = df[column].copy()
    df[target_col] = df[column].apply(lambda x: normalize_region(x, region_map))
    changed_mask = before.astype(str) != df[target_col].astype(str)
    changed_count = int(changed_mask.sum())
    
    unique_before = before.nunique()
    unique_after = df[target_col].nunique()
    click.echo(f"  共处理 {input_rows} 条记录, 影响 {changed_count} 行")
    click.echo(f"  去重前: {unique_before} 种 -> 去重后: {unique_after} 种")
    
    sample = df[[column, target_col]].drop_duplicates().head(10)
    click.echo("  示例映射:")
    for _, row in sample.iterrows():
        if str(row[column]) != str(row[target_col]):
            click.echo(f"    {row[column]} -> {row[target_col]}")
    
    if not preview:
        new_survey = SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            sheet_name=survey.sheet_name,
            metadata=survey.metadata,
            round_num=survey.round_num,
        )
        ws.add_survey(new_survey)
        changes.append(f"统一地区写法: {column} -> {target_col}, 影响 {changed_count} 行")
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='clean region',
            params={'survey': survey_id, 'column': column, 'new_column': new_column},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=changes,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[target_col],
            affected_rows=changed_count,
        )
        ws.add_log(log)
        click.echo(f"\n已更新问卷: {survey.name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@clean_group.command('rename')
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--pattern', '-p', default=None, help='文件名模式 (如: "问卷_{序号:03d}")')
@click.option('--start', '-s', type=int, default=1, help='起始序号')
@click.option('--extensions', '-e', default=None, help='指定扩展名，逗号分隔')
@click.pass_context
def clean_rename(ctx, directory: Path, pattern: str, start: int, extensions: str):
    """批量重命名附件
    
    DIRECTORY: 附件目录
    """
    preview = ctx.obj['preview']
    
    ext_list = [e.strip() for e in extensions.split(',')] if extensions else None
    files = get_file_list(directory, ext_list)
    
    if not files:
        click.echo("未找到可重命名的文件")
        return
    
    click.echo(f"找到 {len(files)} 个文件")
    
    name_pattern = pattern or "file_{index:03d}"
    changes = []
    
    for i, f in enumerate(files, start=start):
        new_name = name_pattern.format(index=i, original=f.stem)
        new_name = safe_filename(new_name)
        new_path = f.parent / f"{new_name}{f.suffix}"
        
        if f != new_path:
            click.echo(f"  {f.name} -> {new_path.name}")
            if not preview:
                if new_path.exists():
                    click.echo(f"    ⚠ 目标文件已存在，跳过: {new_path.name}")
                else:
                    shutil.move(str(f), str(new_path))
                    changes.append(f"重命名: {f.name} -> {new_path.name}")
    
    click.echo(f"\n共处理 {len(files)} 个文件{' (预览模式，未修改)' if preview else ''}")


@clean_group.command('whitespace')
@click.argument('survey_id')
@click.option('--columns', '-c', default=None, help='指定列名，逗号分隔 (默认全部)')
@click.pass_context
def clean_whitespace(ctx, survey_id: str, columns: str):
    """清理文本前后空白
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df.copy()
    cols = [c.strip() for c in columns.split(',')] if columns else list(df.columns)
    input_rows = len(df)
    changes = []
    modified_cols = []
    
    total_changed = 0
    for col in cols:
        if col in df.columns and df[col].dtype == object:
            before = df[col].copy()
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
            changed_mask = before.astype(str) != df[col].astype(str)
            changed = int(changed_mask.sum())
            if changed > 0:
                total_changed += changed
                modified_cols.append(col)
                click.echo(f"  {col}: 清理了 {changed} 处空白")
    
    click.echo(f"\n共处理 {input_rows} 行, 修改 {len(modified_cols)} 列, 影响 {total_changed} 处")
    
    if not preview:
        new_survey = SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            sheet_name=survey.sheet_name,
            metadata=survey.metadata,
            round_num=survey.round_num,
        )
        ws.add_survey(new_survey)
        changes.append(f"清理空白字符: {', '.join(modified_cols)}, 影响 {total_changed} 处")
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='clean whitespace',
            params={'survey': survey_id, 'columns': columns},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=changes,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified_cols,
            affected_rows=total_changed,
        )
        ws.add_log(log)
