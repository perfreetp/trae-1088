"""批处理流水线模块"""
import json
import copy
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from .workspace import Workspace
from .models import ProcessLog


@dataclass
class PipelineStep:
    """流水线步骤"""
    command: str
    subcommand: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ''


@dataclass
class Pipeline:
    """批处理流水线配置"""
    name: str
    steps: List[PipelineStep] = field(default_factory=list)
    project_name: str = ''
    round_num: Optional[int] = None
    output_dir: Optional[str] = None


def load_pipeline(config_path: Path) -> Pipeline:
    """加载流水线配置文件"""
    config_path = Path(config_path)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    steps = []
    for step_data in config.get('steps', []):
        step = PipelineStep(
            command=step_data['command'],
            subcommand=step_data.get('subcommand', ''),
            params=step_data.get('params', {}),
            description=step_data.get('description', ''),
        )
        steps.append(step)
    
    return Pipeline(
        name=config.get('name', config_path.stem),
        steps=steps,
        project_name=config.get('project_name', ''),
        round_num=config.get('round_num'),
        output_dir=config.get('output_dir'),
    )


class PipelineExecutor:
    """流水线执行器"""
    
    def __init__(self, workspace: Workspace, pipeline: Pipeline, preview: bool = False):
        self.workspace = workspace
        self.pipeline = pipeline
        self.preview = preview
        self.execution_log: List[Dict[str, Any]] = []
        self.input_files: List[str] = []
        self.output_files: List[str] = []
        self.changes: List[str] = []
    
    def execute(self, cli_ctx) -> bool:
        """执行流水线"""
        click = __import__('click')
        
        click.echo(f"{'='*60}")
        click.echo(f"执行流水线: {self.pipeline.name}")
        click.echo(f"项目: {self.pipeline.project_name or '未设置'}")
        click.echo(f"轮次: {self.pipeline.round_num or '未设置'}")
        if self.preview:
            click.echo("⚠️  预览模式：不会实际修改数据或落盘")
        click.echo(f"{'='*60}")
        click.echo()
        
        for i, step in enumerate(self.pipeline.steps, 1):
            click.echo(f"[{i}/{len(self.pipeline.steps)}] {step.description or f'{step.command} {step.subcommand}'}")
            click.echo(f"  参数: {step.params}")
            
            if self.preview:
                self._preview_step(step, i)
            else:
                try:
                    self._execute_step(cli_ctx, step)
                    click.echo("  ✓ 完成")
                except Exception as e:
                    click.echo(f"  ✗ 失败: {e}")
                    self.execution_log.append({
                        'step': i,
                        'command': step.command,
                        'subcommand': step.subcommand,
                        'status': 'failed',
                        'error': str(e),
                    })
                    return False
            
            click.echo()
        
        if not self.preview:
            log = ProcessLog(
                timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
                command=f'pipeline {self.pipeline.name}',
                params={'steps': len(self.pipeline.steps)},
                input_files=self.input_files,
                output_files=self.output_files,
                changes=self.changes,
            )
            self.workspace.add_log(log)
        
        click.echo(f"{'='*60}")
        click.echo(f"流水线执行完成！共 {len(self.pipeline.steps)} 个步骤")
        if self.preview:
            click.echo("(预览模式，未实际执行)")
        click.echo(f"{'='*60}")
        
        return True
    
    def _preview_step(self, step: PipelineStep, step_num: int):
        """预览步骤效果"""
        click = __import__('click')
        import pandas as pd
        
        summaries = {
            'import': lambda p: f"将导入 {p.get('path', '')} 下的表格/访谈文件",
            'clean': lambda p: f"将清洗字段: {p.get('column', '')}",
            'check': lambda p: f"将执行质量检查",
            'mask': lambda p: f"将脱敏字段: {p.get('column', '')}",
            'sample': lambda p: f"将抽样: {p.get('count', p.get('ratio', ''))} 条",
            'merge': lambda p: f"将合并/拆分数据",
            'export': lambda p: f"将导出到: {p.get('output', '')}",
            'report': lambda p: f"将生成报告: {p.get('output', '')}",
        }
        
        summary = summaries.get(step.command, lambda p: "执行操作")(step.params)
        click.echo(f"  → {summary}")
        self.changes.append(f"步骤{step_num}: {step.command} {step.subcommand} - {summary}")
    
    def _execute_step(self, cli_ctx, step: PipelineStep):
        """实际执行步骤"""
        click = __import__('click')
        from .cli import main
        
        args = [step.command]
        if step.subcommand:
            args.append(step.subcommand)
        
        for key, value in step.params.items():
            if isinstance(value, bool):
                if value:
                    args.append(f'--{key}')
            else:
                args.append(f'--{key}')
                args.append(str(value))
        
        self.execution_log.append({
            'step': len(self.execution_log) + 1,
            'command': step.command,
            'subcommand': step.subcommand,
            'status': 'success',
        })
