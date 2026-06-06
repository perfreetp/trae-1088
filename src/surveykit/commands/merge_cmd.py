"""merge 命令组 - 合并多轮问卷、拆分访谈逐字稿"""
import click
import pandas as pd
from pathlib import Path
from datetime import datetime
import re

from ..models import SurveyData, InterviewData, ProcessLog
from ..utils import safe_filename
from ..workspace import Workspace


@click.group('merge')
@click.pass_context
def merge_group(ctx):
    """合并多轮问卷、拆分访谈逐字稿"""
    pass


@merge_group.command('surveys')
@click.argument('surveys', nargs=-1, required=True)
@click.option('--output', '-o', required=True, help='合并后问卷名称')
@click.option('--on', '-k', default=None, help='关联键列名，逗号分隔 (默认按行合并)')
@click.option('--how', type=click.Choice(['outer', 'inner', 'left', 'right']), default='outer', help='合并方式')
@click.pass_context
def merge_surveys(ctx, surveys: tuple, output: str, on: str, how: str):
    """合并多轮问卷
    
    SURVEYS: 要合并的问卷ID列表
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    survey_list = []
    for sid in surveys:
        survey = ws.get_survey(sid)
        if survey:
            survey_list.append(survey)
        else:
            click.echo(f"  ⚠ 未找到问卷: {sid}")
    
    if len(survey_list) < 2:
        click.echo("至少需要2个问卷才能合并")
        return
    
    click.echo(f"合并 {len(survey_list)} 个问卷: {', '.join([s.name for s in survey_list])}")
    
    if on:
        keys = [k.strip() for k in on.split(',')]
        merged_df = survey_list[0].df
        for i, survey in enumerate(survey_list[1:], 1):
            merged_df = pd.merge(merged_df, survey.df, on=keys, how=how, suffixes=('', f'_round{i+1}'))
            click.echo(f"  合并第 {i+1} 轮: {len(merged_df)} 行")
    else:
        dfs = []
        for i, survey in enumerate(survey_list):
            df = survey.df.copy()
            df['_round'] = survey.round_num or (i + 1)
            dfs.append(df)
        merged_df = pd.concat(dfs, ignore_index=True)
        click.echo(f"  按行合并: {len(merged_df)} 行")
    
    input_rows = sum(len(s.df) for s in survey_list)
    output_rows = len(merged_df)
    click.echo(f"  结果: {output_rows} 行, {len(merged_df.columns)} 列")
    
    if not preview:
        merged_survey = SurveyData(
            name=safe_filename(output),
            df=merged_df,
            source_path=survey_list[0].source_path,
            metadata={'merged_from': [s.name for s in survey_list]},
        )
        ws.add_survey(merged_survey)
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='merge surveys',
            params={'surveys': list(surveys), 'output': output, 'on': on, 'how': how},
            input_files=[str(s.source_path) for s in survey_list],
            output_files=[],
            changes=[f"合并问卷: {', '.join(surveys)} ({input_rows}行) -> {output} ({output_rows}行)"],
            input_row_count=input_rows,
            output_row_count=output_rows,
            modified_columns=[],
            affected_rows=output_rows,
        )
        ws.add_log(log)
        click.echo(f"\n已创建合并问卷: {output}")
    else:
        click.echo(f"\n(预览模式，未保存)")


@merge_group.command('split-interview')
@click.argument('interview_id')
@click.option('--output-dir', '-o', type=click.Path(path_type=Path), default=None, help='输出目录')
@click.option('--pattern', '-p', default=r'^([^：:：]+)[:：]\s*(.*)$', help='说话人匹配正则')
@click.pass_context
def split_interview(ctx, interview_id: str, output_dir: Path, pattern: str):
    """拆分访谈逐字稿按说话人
    
    INTERVIEW_ID: 访谈ID
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    interview = ws.get_interview(interview_id)
    if not interview:
        click.echo(f"未找到访谈: {interview_id}")
        return
    
    lines = interview.content.split('\n')
    speaker_lines = {}
    current_speaker = None
    current_text = []
    
    regex = re.compile(pattern)
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = regex.match(line)
        if match:
            if current_speaker and current_text:
                if current_speaker not in speaker_lines:
                    speaker_lines[current_speaker] = []
                speaker_lines[current_speaker].extend(current_text)
                current_text = []
            
            current_speaker = match.group(1).strip()
            text = match.group(2).strip()
            if text:
                current_text.append(text)
        elif current_speaker:
            current_text.append(line)
    
    if current_speaker and current_text:
        if current_speaker not in speaker_lines:
            speaker_lines[current_speaker] = []
        speaker_lines[current_speaker].extend(current_text)
    
    click.echo(f"识别到 {len(speaker_lines)} 位说话人:")
    for speaker, texts in speaker_lines.items():
        click.echo(f"  - {speaker}: {len(texts)} 句话, {sum(len(t) for t in texts)} 字符")
    
    if not preview and output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        output_files = []
        for speaker, texts in speaker_lines.items():
            safe_name = safe_filename(speaker)
            file_path = out_dir / f"{interview_id}_{safe_name}.txt"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(texts))
            output_files.append(str(file_path))
        
        log = ProcessLog(
            timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
            command='merge split-interview',
            params={'interview': interview_id, 'pattern': pattern},
            input_files=[str(interview.source_path)],
            output_files=output_files,
            changes=[f"拆分访谈: {interview_id} -> {len(speaker_lines)} 个文件"],
        )
        ws.add_log(log)
        click.echo(f"\n已导出到: {out_dir}{' (预览模式，未保存)' if preview else ''}")
