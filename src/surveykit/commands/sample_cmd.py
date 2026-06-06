"""sample 命令组 - 按规则抽样"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
import random

from ..models import SurveyData, ProcessLog
from ..utils import safe_filename
from ..workspace import Workspace


@click.group('sample')
@click.pass_context
def sample_group(ctx):
    """按规则抽样"""
    pass


@sample_group.command('random')
@click.argument('survey_id')
@click.option('--count', '-n', type=int, default=None, help='抽样数量')
@click.option('--ratio', '-r', type=float, default=None, help='抽样比例 (0-1)，与count二选一')
@click.option('--output', '-o', default=None, help='输出问卷名称')
@click.option('--seed', type=int, default=None, help='随机种子')
@click.pass_context
def sample_random(ctx, survey_id: str, count: int, ratio: float, output: str, seed: int):
    """随机抽样
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    input_rows = len(df)
    
    if count is None and ratio is None:
        ratio = 0.1
    
    if ratio is not None:
        count = max(1, int(input_rows * ratio))
    
    if count >= input_rows:
        click.echo(f"抽样数量 ({count}) >= 总体数量 ({input_rows})，返回全部")
        sampled_df = df.copy()
    else:
        sampled_df = df.sample(n=count, random_state=seed)
    
    output_rows = len(sampled_df)
    click.echo(f"抽样: {input_rows} -> {output_rows}")
    
    out_name = output or f"{survey_id}_sample_{output_rows}"
    
    if not preview:
        sampled_survey = SurveyData(
            name=safe_filename(out_name),
            df=sampled_df,
            source_path=survey.source_path,
            metadata={'sampled_from': survey_id, 'sample_count': output_rows, 'method': 'random', 'ratio': ratio},
        )
        ws.add_survey(sampled_survey)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='sample random',
            params={'survey': survey_id, 'count': output_rows, 'ratio': ratio, 'seed': seed},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"随机抽样: {survey_id} ({input_rows}行) -> {out_name} ({output_rows}行)"],
            input_row_count=input_rows,
            output_row_count=output_rows,
            modified_columns=[],
            affected_rows=output_rows,
        )
        ws.add_log(log)
        click.echo(f"\n已创建抽样问卷: {out_name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@sample_group.command('stratified')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='分层列名')
@click.option('--ratio', '-r', type=float, default=0.1, help='抽样比例 (0-1)')
@click.option('--count', '-n', type=int, default=None, help='每层抽样数量 (与ratio二选一)')
@click.option('--output', '-o', default=None, help='输出问卷名称')
@click.option('--seed', type=int, default=None, help='随机种子')
@click.pass_context
def sample_stratified(ctx, survey_id: str, column: str, ratio: float, count: int, output: str, seed: int):
    """分层抽样
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    if column not in df.columns:
        click.echo(f"列不存在: {column}")
        return
    
    groups = df.groupby(column)
    click.echo(f"分层列 '{column}' 有 {len(groups)} 个组:")
    
    sampled_parts = []
    for name, group in groups:
        n = count or max(1, int(len(group) * ratio))
        n = min(n, len(group))
        sampled = group.sample(n=n, random_state=seed)
        sampled_parts.append(sampled)
        click.echo(f"  {name}: {len(group)} -> {len(sampled)}")
    
    sampled_df = pd.concat(sampled_parts, ignore_index=True)
    click.echo(f"\n总抽样: {len(df)} -> {len(sampled_df)}")
    
    input_rows = len(df)
    output_rows = len(sampled_df)
    
    out_name = output or f"{survey_id}_stratified_{column}"
    
    if not preview:
        sampled_survey = SurveyData(
            name=safe_filename(out_name),
            df=sampled_df,
            source_path=survey.source_path,
            metadata={'sampled_from': survey_id, 'stratify_by': column, 'ratio': ratio, 'count': count},
        )
        ws.add_survey(sampled_survey)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='sample stratified',
            params={'survey': survey_id, 'column': column, 'ratio': ratio, 'count': count},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"分层抽样: {survey_id} ({input_rows}行) -> {out_name} ({output_rows}行)"],
            input_row_count=input_rows,
            output_row_count=output_rows,
            modified_columns=[],
            affected_rows=output_rows,
        )
        ws.add_log(log)
        click.echo(f"\n已创建抽样问卷: {out_name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@sample_group.command('systematic')
@click.argument('survey_id')
@click.option('--interval', '-k', type=int, required=True, help='抽样间隔')
@click.option('--start', '-s', type=int, default=0, help='起始位置')
@click.option('--output', '-o', default=None, help='输出问卷名称')
@click.pass_context
def sample_systematic(ctx, survey_id: str, interval: int, start: int, output: str):
    """系统抽样（等距抽样）
    
    SURVEY_ID: 问卷ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey = ws.get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    df = survey.df
    indices = list(range(start, len(df), interval))
    sampled_df = df.iloc[indices].reset_index(drop=True)
    
    click.echo(f"系统抽样: 间隔 {interval}, 起始 {start}")
    click.echo(f"  {len(df)} -> {len(sampled_df)}")
    
    input_rows = len(df)
    output_rows = len(sampled_df)
    
    out_name = output or f"{survey_id}_systematic_k{interval}"
    
    if not preview:
        sampled_survey = SurveyData(
            name=safe_filename(out_name),
            df=sampled_df,
            source_path=survey.source_path,
            metadata={'sampled_from': survey_id, 'interval': interval, 'start': start},
        )
        ws.add_survey(sampled_survey)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='sample systematic',
            params={'survey': survey_id, 'interval': interval, 'start': start},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"系统抽样: {survey_id} ({input_rows}行) -> {out_name} ({output_rows}行)"],
            input_row_count=input_rows,
            output_row_count=output_rows,
            modified_columns=[],
            affected_rows=output_rows,
        )
        ws.add_log(log)
        click.echo(f"\n已创建抽样问卷: {out_name}")
    else:
        click.echo(f"\n(预览模式，未保存)")
