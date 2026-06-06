"""SurveyKit 命令行接口"""
import click
from datetime import datetime
from pathlib import Path

from .workspace import Workspace
from . import __version__


def get_workspace(ctx) -> Workspace:
    """从上下文获取工作区"""
    return ctx.obj['workspace']


@click.group()
@click.version_option(__version__, '-v', '--version')
@click.option('--workspace', '-w', type=click.Path(path_type=Path), default=None,
              help='工作区目录 (默认: ./.surveykit)')
@click.option('--preview', is_flag=True, help='预览模式，不修改原文件')
@click.pass_context
def main(ctx, workspace, preview):
    """SurveyKit - 高校课题组问卷访谈资料整理工具
    
    提供 import、check、clean、merge、sample、mask、export、report 8 组命令
    """
    ctx.ensure_object(dict)
    ctx.obj['workspace'] = Workspace(workspace)
    ctx.obj['preview'] = preview


@main.command()
@click.pass_context
def status(ctx):
    """显示工作区状态"""
    ws = get_workspace(ctx)
    surveys = ws.list_surveys()
    interviews = ws.list_interviews()
    
    click.echo(f"工作区: {ws.root}")
    click.echo(f"问卷数量: {len(surveys)}")
    click.echo(f"访谈数量: {len(interviews)}")
    
    if surveys:
        click.echo("\n问卷列表:")
        for s in surveys:
            click.echo(f"  - {s['name']} ({s['row_count']} 行, {len(s['columns'])} 列)")
    
    if interviews:
        click.echo("\n访谈列表:")
        for i in interviews:
            click.echo(f"  - {i['name']}")


from .commands.import_cmd import import_group
from .commands.check_cmd import check_group
from .commands.clean_cmd import clean_group
from .commands.merge_cmd import merge_group
from .commands.sample_cmd import sample_group
from .commands.mask_cmd import mask_group
from .commands.export_cmd import export_group
from .commands.report_cmd import report_group
from .commands.run_cmd import run_group

main.add_command(import_group)
main.add_command(check_group)
main.add_command(clean_group)
main.add_command(merge_group)
main.add_command(sample_group)
main.add_command(mask_group)
main.add_command(export_group)
main.add_command(report_group)
main.add_command(run_group)


if __name__ == '__main__':
    main()
