"""mask 命令组 - 脱敏处理"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime

from ..models import SurveyData, ProcessLog
from ..utils import mask_name, mask_phone, mask_id_card
from ..workspace import Workspace


@click.group('mask')
@click.pass_context
def mask_group(ctx):
    """脱敏处理：姓名、电话、身份证号"""
    pass


@mask_group.command('name')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='姓名列名')
@click.option('--new-column', '-n', default=None, help='新列名 (默认覆盖原列)')
@click.pass_context
def mask_name_cmd(ctx, survey_id: str, column: str, new_column: str):
    """姓名脱敏
    
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
    
    target_col = new_column or column
    input_rows = len(df)
    
    before = df[column].copy()
    df[target_col] = df[column].apply(mask_name)
    changed_mask = before.astype(str) != df[target_col].astype(str)
    changed_count = int(changed_mask.sum())
    
    click.echo(f"姓名脱敏: {column} -> {target_col}")
    click.echo(f"  共处理 {input_rows} 条记录, 影响 {changed_count} 行")
    sample = df[[column, target_col]].head(10)
    for _, row in sample.iterrows():
        val = row[column]
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        if pd.notna(val) and str(val).strip():
            target_val = row[target_col]
            if isinstance(target_val, pd.Series):
                target_val = target_val.iloc[0]
            click.echo(f"  {val} -> {target_val}")
    
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
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='mask name',
            params={'survey': survey_id, 'column': column, 'new_column': new_column},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"姓名脱敏: {column}, 影响 {changed_count} 行"],
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[target_col],
            affected_rows=changed_count,
        )
        ws.add_log(log)
        click.echo(f"\n已更新问卷: {survey.name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@mask_group.command('phone')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='手机号列名')
@click.option('--new-column', '-n', default=None, help='新列名 (默认覆盖原列)')
@click.pass_context
def mask_phone_cmd(ctx, survey_id: str, column: str, new_column: str):
    """手机号脱敏
    
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
    
    target_col = new_column or column
    input_rows = len(df)
    
    before = df[column].copy()
    df[target_col] = df[column].apply(mask_phone)
    changed_mask = before.astype(str) != df[target_col].astype(str)
    changed_count = int(changed_mask.sum())
    
    click.echo(f"手机号脱敏: {column} -> {target_col}")
    click.echo(f"  共处理 {input_rows} 条记录, 影响 {changed_count} 行")
    sample = df[[column, target_col]].head(10)
    for _, row in sample.iterrows():
        val = row[column]
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        if pd.notna(val) and str(val).strip():
            target_val = row[target_col]
            if isinstance(target_val, pd.Series):
                target_val = target_val.iloc[0]
            click.echo(f"  {val} -> {target_val}")
    
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
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='mask phone',
            params={'survey': survey_id, 'column': column, 'new_column': new_column},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"手机号脱敏: {column}, 影响 {changed_count} 行"],
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[target_col],
            affected_rows=changed_count,
        )
        ws.add_log(log)
        click.echo(f"\n已更新问卷: {survey.name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@mask_group.command('idcard')
@click.argument('survey_id')
@click.option('--column', '-c', required=True, help='身份证号列名')
@click.option('--new-column', '-n', default=None, help='新列名 (默认覆盖原列)')
@click.pass_context
def mask_idcard_cmd(ctx, survey_id: str, column: str, new_column: str):
    """身份证号脱敏
    
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
    
    target_col = new_column or column
    input_rows = len(df)
    
    before = df[column].copy()
    df[target_col] = df[column].apply(mask_id_card)
    changed_mask = before.astype(str) != df[target_col].astype(str)
    changed_count = int(changed_mask.sum())
    
    click.echo(f"身份证号脱敏: {column} -> {target_col}")
    click.echo(f"  共处理 {input_rows} 条记录, 影响 {changed_count} 行")
    sample = df[[column, target_col]].head(10)
    for _, row in sample.iterrows():
        val = row[column]
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        if pd.notna(val) and str(val).strip():
            target_val = row[target_col]
            if isinstance(target_val, pd.Series):
                target_val = target_val.iloc[0]
            click.echo(f"  {val} -> {target_val}")
    
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
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='mask idcard',
            params={'survey': survey_id, 'column': column, 'new_column': new_column},
            input_files=[str(survey.source_path)],
            output_files=[],
            changes=[f"身份证号脱敏: {column}, 影响 {changed_count} 行"],
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[target_col],
            affected_rows=changed_count,
        )
        ws.add_log(log)
        click.echo(f"\n已更新问卷: {survey.name}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@mask_group.command('all')
@click.argument('survey_id')
@click.option('--name-col', default='姓名', help='姓名列名')
@click.option('--phone-col', default='电话', help='电话列名')
@click.option('--id-col', default='身份证', help='身份证列名')
@click.pass_context
def mask_all(ctx, survey_id: str, name_col: str, phone_col: str, id_col: str):
    """一键脱敏所有敏感字段
    
    SURVEY_ID: 问卷ID
    """
    click.echo(f"对问卷 {survey_id} 执行全面脱敏")
    
    survey = ctx.obj['workspace'].get_survey(survey_id)
    if not survey:
        click.echo(f"未找到问卷: {survey_id}")
        return
    
    cols = survey.columns
    if name_col in cols:
        click.echo(f"\n--- 姓名脱敏 ({name_col}) ---")
        ctx.invoke(mask_name_cmd, survey_id=survey_id, column=name_col, new_column=None)
    
    if phone_col in cols:
        click.echo(f"\n--- 电话脱敏 ({phone_col}) ---")
        ctx.invoke(mask_phone_cmd, survey_id=survey_id, column=phone_col, new_column=None)
    
    if id_col in cols:
        click.echo(f"\n--- 身份证脱敏 ({id_col}) ---")
        ctx.invoke(mask_idcard_cmd, survey_id=survey_id, column=id_col, new_column=None)
    
    click.echo("\n脱敏完成")
