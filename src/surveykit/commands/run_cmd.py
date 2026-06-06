"""run 命令组 - 批处理流水线和完整交付包导出"""
import click
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

from ..pipeline import load_pipeline, PipelineExecutor
from ..models import ProcessLog
from ..workspace import Workspace


@click.group('run')
@click.pass_context
def run_group(ctx):
    """批处理流水线、完整交付包导出"""
    pass


@run_group.command('pipeline')
@click.argument('config', type=click.Path(exists=True, path_type=Path))
@click.option('--preview', is_flag=True, help='预览模式，展示计划但不执行')
@click.pass_context
def run_pipeline(ctx, config: Path, preview: bool):
    """执行批处理流水线
    
    CONFIG: 流水线配置文件路径 (JSON)
    """
    ws: Workspace = ctx.obj['workspace']
    is_preview = ctx.obj.get('preview', False) or preview
    
    try:
        pipeline = load_pipeline(config)
    except Exception as e:
        click.echo(f"加载流水线配置失败: {e}")
        return
    
    executor = PipelineExecutor(ws, pipeline, is_preview)
    executor.execute(ctx)


@run_group.command('delivery')
@click.option('--project', '-p', default='项目', help='项目名称')
@click.option('--round', 'round_num', type=int, default=None, help='问卷轮次')
@click.option('--output', '-o', type=click.Path(path_type=Path), required=True, help='交付包输出目录')
@click.option('--template', '-t', type=click.Path(exists=True, path_type=Path), default=None, help='检查模板路径')
@click.option('--include-interviews', is_flag=True, help='包含访谈数据')
@click.pass_context
def run_delivery(ctx, project: str, round_num: int, output: Path, template: Path, include_interviews: bool):
    """一键生成完整交付包
    
    包含：清洗后问卷、访谈文本、异常清单、完成率报告、处理日志、汇总说明
    """
    ws: Workspace = ctx.obj['workspace']
    preview = ctx.obj['preview']
    
    output_dir = Path(output)
    timestamp = datetime.now().strftime('%Y%m%d')
    
    round_str = f"_第{round_num}轮" if round_num else ""
    package_name = f"{project}{round_str}_交付包_{timestamp}"
    package_dir = output_dir / package_name
    
    click.echo(f"生成交付包: {package_name}")
    click.echo(f"输出目录: {package_dir}")
    if preview:
        click.echo("⚠️  预览模式，不实际生成文件")
    click.echo()
    
    surveys = ws.list_surveys()
    interviews = ws.list_interviews() if include_interviews else []
    
    if not surveys:
        click.echo("工作区中没有问卷数据，请先导入")
        return
    
    subdirs = ['01_清洗后数据', '02_访谈文本', '03_质量检查', '04_统计报告', '05_处理日志']
    
    if preview:
        click.echo("将创建以下目录结构:")
        for sd in subdirs:
            click.echo(f"  ├── {sd}/")
        click.echo(f"  └── 00_汇总说明.txt")
        click.echo()
        
        click.echo("将包含的文件:")
        for s in surveys:
            click.echo(f"  - 01_清洗后数据/{s['name']}.xlsx")
        if include_interviews:
            for i in interviews:
                click.echo(f"  - 02_访谈文本/{i['name']}.txt")
        if template:
            click.echo(f"  - 03_质量检查/异常清单.xlsx")
        click.echo(f"  - 04_统计报告/题目完成率.xlsx")
        click.echo(f"  - 04_统计报告/数据汇总.json")
        click.echo(f"  - 05_处理日志/处理历史.json")
        return
    
    package_dir.mkdir(parents=True, exist_ok=True)
    for sd in subdirs:
        (package_dir / sd).mkdir(exist_ok=True)
    
    click.echo("1. 导出清洗后问卷...")
    for s in surveys:
        survey = ws.get_survey(s['name'])
        if survey:
            out_path = package_dir / '01_清洗后数据' / f"{survey.name}.xlsx"
            survey.df.to_excel(out_path, index=False)
            click.echo(f"  ✓ {survey.name}.xlsx")
    
    if include_interviews:
        click.echo("\n2. 导出访谈文本...")
        for i in interviews:
            interview = ws.get_interview(i['name'])
            if interview:
                out_path = package_dir / '02_访谈文本' / f"{interview.name}.txt"
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(interview.content)
                click.echo(f"  ✓ {interview.name}.txt")
    
    if template:
        click.echo("\n3. 生成异常清单（按模板）...")
        from ..template import load_template, validate_with_template
        all_issues = []
        for s in surveys:
            survey = ws.get_survey(s['name'])
            if survey:
                tmpl = load_template(template)
                issues, _ = validate_with_template(survey.df, tmpl)
                for issue in issues:
                    issue['survey'] = survey.name
                    all_issues.append(issue)
        
        if all_issues:
            issues_df = pd.DataFrame(all_issues)
            out_path = package_dir / '03_质量检查' / '异常清单.xlsx'
            issues_df.to_excel(out_path, index=False)
            click.echo(f"  ✓ 异常清单.xlsx ({len(all_issues)} 条)")
        else:
            click.echo("  ✓ 无异常")
    
    click.echo("\n4. 生成统计报告...")
    completion_data = []
    for s in surveys:
        survey = ws.get_survey(s['name'])
        if survey:
            df = survey.df
            for col in df.columns:
                completion_rate = df[col].notna().mean()
                completion_data.append({
                    '问卷': survey.name,
                    '题目': col,
                    '总题数': len(df),
                    '已答题数': int(df[col].notna().sum()),
                    '完成率': round(completion_rate, 4),
                })
    
    if completion_data:
        comp_df = pd.DataFrame(completion_data)
        out_path = package_dir / '04_统计报告' / '题目完成率.xlsx'
        comp_df.to_excel(out_path, index=False)
        click.echo("  ✓ 题目完成率.xlsx")
    
    summary = {
        '项目名称': project,
        '生成时间': datetime.now().isoformat(),
        '轮次': round_num,
        '问卷数量': len(surveys),
        '访谈数量': len(interviews),
        '问卷详情': [
            {'名称': s['name'], '行数': s['row_count'], '列数': len(s['columns'])}
            for s in surveys
        ],
    }
    out_path = package_dir / '04_统计报告' / '数据汇总.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    click.echo("  ✓ 数据汇总.json")
    
    click.echo("\n5. 导出处理日志...")
    log_dir = ws.root / 'logs'
    log_files = sorted(log_dir.glob('*.json'))
    all_logs = []
    for lf in log_files:
        with open(lf, 'r', encoding='utf-8') as f:
            all_logs.append(json.load(f))
    
    if all_logs:
        out_path = package_dir / '05_处理日志' / '处理历史.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(all_logs, f, ensure_ascii=False, indent=2)
        click.echo(f"  ✓ 处理历史.json ({len(all_logs)} 条)")
    
    click.echo("\n6. 生成汇总说明...")
    readme_content = f"""# {project} 数据交付说明

## 基本信息
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 问卷轮次: 第{round_num}轮" if round_num else "未指定
- 问卷数量: {len(surveys)} 份
- 访谈数量: {len(interviews)} 份

## 目录说明
- 01_清洗后数据: 经过清洗和脱敏的问卷数据
- 02_访谈文本: 拆分后的访谈逐字稿
- 03_质量检查: 异常清单和质量检查结果
- 04_统计报告: 题目完成率和数据汇总
- 05_处理日志: 所有数据处理操作历史

## 备注
本交付包由 SurveyKit 自动生成
"""
    readme_path = package_dir / '00_汇总说明.txt'
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    click.echo("  ✓ 00_汇总说明.txt")
    
    click.echo(f"\n✅ 交付包已生成: {package_dir}")
