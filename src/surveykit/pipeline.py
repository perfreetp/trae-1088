"""批处理流水线模块"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

import pandas as pd

from .workspace import Workspace
from .models import ProcessLog, SurveyData, InterviewData
from .utils import normalize_date, normalize_region, mask_name, mask_phone, mask_id_card, is_empty


@dataclass
class PipelineStep:
    """流水线步骤"""
    command: str
    subcommand: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ''


@dataclass
class StepResult:
    """步骤执行结果"""
    success: bool
    input_row_count: Optional[int] = None
    output_row_count: Optional[int] = None
    modified_columns: List[str] = field(default_factory=list)
    affected_rows: Optional[int] = None
    output_files: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class Pipeline:
    """批处理流水线配置"""
    name: str
    steps: List[PipelineStep] = field(default_factory=list)
    project_name: str = ''
    round_num: Optional[int] = None
    output_dir: Optional[str] = None


def _get_param(params: Dict[str, Any], *aliases: str, default: Any = None) -> Any:
    """获取参数，支持多个别名"""
    for alias in aliases:
        if alias in params:
            return params[alias]
    return default


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
        self.all_input_files: List[str] = []
        self.all_output_files: List[str] = []
        self.all_changes: List[str] = []
        self.step_results: List[StepResult] = []
    
    def execute(self, cli_ctx=None) -> bool:
        """执行流水线"""
        import click
        
        click.echo(f"{'='*60}")
        click.echo(f"执行流水线: {self.pipeline.name}")
        click.echo(f"项目: {self.pipeline.project_name or '未设置'}")
        click.echo(f"轮次: {self.pipeline.round_num or '未设置'}")
        if self.preview:
            click.echo("⚠️  预览模式：不会实际修改数据或落盘")
        click.echo(f"{'='*60}")
        click.echo()
        
        for i, step in enumerate(self.pipeline.steps, 1):
            step_desc = step.description or f'{step.command} {step.subcommand}'
            click.echo(f"[{i}/{len(self.pipeline.steps)}] {step_desc}")
            if not self.preview:
                click.echo(f"  命令: {step.command} {step.subcommand}")
                click.echo(f"  参数: {step.params}")
            
            result = None
            try:
                if self.preview:
                    result = self._preview_step(step)
                else:
                    result = self._execute_step(step)
                
                if result.success:
                    click.echo("  ✓ 完成")
                    for msg in result.messages:
                        click.echo(f"    {msg}")
                else:
                    click.echo()
                    click.echo("=" * 60)
                    click.echo(f"❌ 流水线执行失败！")
                    click.echo(f"  步骤序号: 第 {i} 步 / 共 {len(self.pipeline.steps)} 步")
                    click.echo(f"  步骤描述: {step_desc}")
                    click.echo(f"  命令类型: {step.command} {step.subcommand}")
                    click.echo(f"  失败原因: {result.error}")
                    click.echo()
                    click.echo("  已成功执行的步骤:")
                    for j in range(i - 1):
                        prev_step = self.pipeline.steps[j]
                        click.echo(f"    第{j+1}步: {prev_step.description or f'{prev_step.command} {prev_step.subcommand}'} ✓")
                    click.echo("=" * 60)
                    return False
                
            except Exception as e:
                click.echo()
                click.echo("=" * 60)
                click.echo(f"❌ 流水线执行异常！")
                click.echo(f"  步骤序号: 第 {i} 步 / 共 {len(self.pipeline.steps)} 步")
                click.echo(f"  步骤描述: {step_desc}")
                click.echo(f"  命令类型: {step.command} {step.subcommand}")
                click.echo(f"  异常信息: {e}")
                click.echo()
                import traceback
                traceback.print_exc()
                click.echo("=" * 60)
                return False
            
            self.step_results.append(result)
            if result:
                self.all_output_files.extend(result.output_files)
                self.all_changes.append(
                    f"步骤{i}: {step.command} {step.subcommand} - "
                    f"输入:{result.input_row_count or '-'}行 → 输出:{result.output_row_count or '-'}行"
                )
            
            click.echo()
        
        if not self.preview:
            log = ProcessLog(
                timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
                command=f'pipeline {self.pipeline.name}',
                params={'steps': len(self.pipeline.steps)},
                input_files=self.all_input_files,
                output_files=self.all_output_files,
                changes=self.all_changes,
            )
            self.workspace.add_log(log)
        
        click.echo(f"{'='*60}")
        click.echo(f"流水线执行完成！共 {len(self.pipeline.steps)} 个步骤")
        if self.preview:
            click.echo("(预览模式，未实际执行)")
        click.echo(f"{'='*60}")
        
        return True
    
    def _preview_step(self, step: PipelineStep) -> StepResult:
        """预览步骤效果"""
        import click
        
        summaries = {
            'import': lambda p: f"将导入 {_get_param(p, 'path', 'file_path', '')} 下的表格/访谈文件",
            'clean': lambda p: f"将清洗字段: {_get_param(p, 'column', 'columns', '')}",
            'check': lambda p: f"将执行质量检查，输出到 {_get_param(p, 'output', '')}",
            'mask': lambda p: f"将脱敏字段: {_get_param(p, 'column', 'columns', '')}",
            'sample': lambda p: f"将抽样: {_get_param(p, 'count', p.get('ratio', ''))} 条",
            'merge': lambda p: f"将合并/拆分数据",
            'export': lambda p: f"将导出到: {_get_param(p, 'output', 'output_path', '')}",
            'report': lambda p: f"将生成报告: {_get_param(p, 'output', 'output_path', '')}",
        }
        
        summary = summaries.get(step.command, lambda p: "执行操作")(step.params)
        click.echo(f"  → {summary}")
        
        return StepResult(success=True, messages=[summary])
    
    def _execute_step(self, step: PipelineStep) -> StepResult:
        """实际执行步骤"""
        cmd = step.command
        sub = step.subcommand
        params = step.params
        
        handlers = {
            ('import', 'table'): self._handle_import_table,
            ('import', 'interview'): self._handle_import_interview,
            ('clean', 'date'): self._handle_clean_date,
            ('clean', 'region'): self._handle_clean_region,
            ('clean', 'whitespace'): self._handle_clean_whitespace,
            ('mask', 'name'): self._handle_mask_name,
            ('mask', 'phone'): self._handle_mask_phone,
            ('mask', 'idcard'): self._handle_mask_idcard,
            ('check', 'missing'): self._handle_check_missing,
            ('check', 'template'): self._handle_check_template,
            ('sample', 'random'): self._handle_sample_random,
            ('sample', 'stratified'): self._handle_sample_stratified,
            ('export', 'survey'): self._handle_export_survey,
            ('export', 'logs'): self._handle_export_logs,
            ('report', 'completion'): self._handle_report_completion,
            ('report', 'anomalies'): self._handle_report_anomalies,
        }
        
        handler = handlers.get((cmd, sub))
        if handler:
            return handler(params)
        else:
            return StepResult(
                success=False,
                error=f"未找到处理函数: {cmd} {sub}",
            )
    
    def _handle_import_table(self, params: Dict[str, Any]) -> StepResult:
        """执行导入表格"""
        path = Path(_get_param(params, 'path', 'file_path'))
        name = _get_param(params, 'name', 'survey_name') or path.stem
        round_num = _get_param(params, 'round', 'round_num')
        
        if not path.exists():
            return StepResult(
                success=False,
                error=f"文件不存在: {path}",
            )
        
        try:
            if path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path, encoding=params.get('encoding', 'utf-8-sig'))
        except Exception as e:
            return StepResult(
                success=False,
                error=f"读取文件失败: {path}, 原因: {e}",
            )
        
        survey = SurveyData(
            name=name,
            df=df,
            source_path=path,
            round_num=round_num,
        )
        self.workspace.add_survey(survey)
        self.all_input_files.append(str(path))
        
        return StepResult(
            success=True,
            input_row_count=len(df),
            output_row_count=len(df),
            modified_columns=[],
            affected_rows=len(df),
            messages=[f"导入 {len(df)} 行, {len(df.columns)} 列 -> 问卷 '{name}'"],
        )
    
    def _handle_import_interview(self, params: Dict[str, Any]) -> StepResult:
        """执行导入访谈"""
        from .utils import read_text_file
        
        path = Path(_get_param(params, 'path', 'file_path'))
        name = _get_param(params, 'name', 'interview_name') or path.stem
        content = read_text_file(path)
        
        interview = InterviewData(
            name=name,
            content=content,
            source_path=path,
        )
        self.workspace.add_interview(interview)
        self.all_input_files.append(str(path))
        
        return StepResult(
            success=True,
            input_row_count=len(content.splitlines()),
            output_row_count=len(content.splitlines()),
            messages=[f"导入访谈 '{name}' ({len(content)} 字符)"],
        )
    
    def _get_survey(self, survey_id: str) -> Optional[SurveyData]:
        return self.workspace.get_survey(survey_id)
    
    def _save_survey(self, survey: SurveyData) -> None:
        self.workspace.add_survey(survey)
    
    def _get_columns(self, params: Dict[str, Any]) -> List[str]:
        """获取列名列表，支持 column 或 columns 参数"""
        col = _get_param(params, 'column')
        cols = _get_param(params, 'columns')
        if cols:
            if isinstance(cols, str):
                return [c.strip() for c in cols.split(',')]
            return cols
        if col:
            return [col]
        return []
    
    def _handle_clean_date(self, params: Dict[str, Any]) -> StepResult:
        """执行日期清洗"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        for col in columns:
            if col not in survey.df.columns:
                return StepResult(
                    success=False,
                    error=f"列不存在: '{col}'，问卷 '{survey_id}' 的可用列: {', '.join(survey.df.columns)}",
                )
        
        df = survey.df.copy()
        input_rows = len(df)
        total_changed = 0
        modified = []
        
        for column in columns:
            if column not in df.columns:
                continue
            before = df[column].copy()
            df[column] = df[column].apply(normalize_date)
            changed_mask = before.astype(str) != df[column].astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                total_changed += changed_count
                modified.append(column)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"标准化日期字段: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_clean_region(self, params: Dict[str, Any]) -> StepResult:
        """执行地区清洗"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        for col in columns:
            if col not in survey.df.columns:
                return StepResult(
                    success=False,
                    error=f"列不存在: '{col}'，问卷 '{survey_id}' 的可用列: {', '.join(survey.df.columns)}",
                )
        
        df = survey.df.copy()
        input_rows = len(df)
        total_changed = 0
        modified = []
        
        for column in columns:
            if column not in df.columns:
                continue
            before = df[column].copy()
            df[column] = df[column].apply(normalize_region)
            changed_mask = before.astype(str) != df[column].astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                total_changed += changed_count
                modified.append(column)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"标准化地区字段: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_clean_whitespace(self, params: Dict[str, Any]) -> StepResult:
        """执行空白清理"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df.copy()
        input_rows = len(df)
        
        cols = columns or list(df.select_dtypes(include=['object']).columns)
        total_changed = 0
        modified = []
        
        for col in cols:
            if col in df.columns and df[col].dtype == object:
                before = df[col].copy()
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
                changed = int((before.astype(str) != df[col].astype(str)).sum())
                if changed > 0:
                    total_changed += changed
                    modified.append(col)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"清理空白: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_mask_name(self, params: Dict[str, Any]) -> StepResult:
        """执行姓名脱敏"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        for col in columns:
            if col not in survey.df.columns:
                return StepResult(
                    success=False,
                    error=f"列不存在: '{col}'，问卷 '{survey_id}' 的可用列: {', '.join(survey.df.columns)}",
                )
        
        df = survey.df.copy()
        input_rows = len(df)
        total_changed = 0
        modified = []
        
        for column in columns:
            if column not in df.columns:
                continue
            before = df[column].copy()
            df[column] = df[column].apply(mask_name)
            changed_mask = before.astype(str) != df[column].astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                total_changed += changed_count
                modified.append(column)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"姓名脱敏: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_mask_phone(self, params: Dict[str, Any]) -> StepResult:
        """执行电话脱敏"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        for col in columns:
            if col not in survey.df.columns:
                return StepResult(
                    success=False,
                    error=f"列不存在: '{col}'，问卷 '{survey_id}' 的可用列: {', '.join(survey.df.columns)}",
                )
        
        df = survey.df.copy()
        input_rows = len(df)
        total_changed = 0
        modified = []
        
        for column in columns:
            if column not in df.columns:
                continue
            before = df[column].copy()
            df[column] = df[column].apply(mask_phone)
            changed_mask = before.astype(str) != df[column].astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                total_changed += changed_count
                modified.append(column)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"电话脱敏: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_mask_idcard(self, params: Dict[str, Any]) -> StepResult:
        """执行身份证脱敏"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        columns = self._get_columns(params)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df.copy()
        input_rows = len(df)
        total_changed = 0
        modified = []
        
        for column in columns:
            if column not in df.columns:
                continue
            before = df[column].copy()
            df[column] = df[column].apply(mask_id_card)
            changed_mask = before.astype(str) != df[column].astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                total_changed += changed_count
                modified.append(column)
        
        self._save_survey(SurveyData(
            name=survey.name,
            df=df,
            source_path=survey.source_path,
            metadata=survey.metadata,
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=modified,
            affected_rows=total_changed,
            messages=[f"身份证脱敏: {', '.join(modified)}, 影响 {total_changed} 行"],
        )
    
    def _handle_check_missing(self, params: Dict[str, Any]) -> StepResult:
        """执行缺失检查"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        threshold = params.get('threshold', 0.0)
        output = _get_param(params, 'output')
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df
        input_rows = len(df)
        issues = []
        
        for col in df.columns:
            missing_mask = df[col].apply(is_empty)
            count = int(missing_mask.sum())
            pct = count / len(df) if len(df) > 0 else 0
            
            if pct > 0 and pct >= threshold:
                missing_rows = [i + 2 for i, is_missing in enumerate(missing_mask) if is_missing]
                issues.append({
                    'column': col,
                    'missing_count': count,
                    'missing_rate': round(pct, 4),
                    'missing_rows': str(missing_rows[:20]),
                    'total_missing_rows': len(missing_rows),
                })
        
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if issues:
                pd.DataFrame(issues).to_excel(out_path, index=False)
            else:
                pd.DataFrame(columns=['column', 'missing_count', 'missing_rate', 'missing_rows', 'total_missing_rows']).to_excel(out_path, index=False)
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[],
            affected_rows=sum(i['missing_count'] for i in issues),
            output_files=[str(output)] if output else [],
            messages=[f"发现 {len(issues)} 个字段有缺失，共影响 {sum(i['missing_count'] for i in issues)} 处"],
        )
    
    def _handle_check_template(self, params: Dict[str, Any]) -> StepResult:
        """执行模板检查"""
        from .template import load_template, validate_with_template
        
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        template_path = Path(_get_param(params, 'template_path', 'template'))
        output = _get_param(params, 'output')
        summary = params.get('summary', False)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        if not template_path.exists():
            return StepResult(success=False, error=f"模板文件不存在: {template_path}")
        
        try:
            template = load_template(template_path)
        except Exception as e:
            return StepResult(success=False, error=f"加载模板失败: {template_path}, 原因: {e}")
        issues, issues_df = validate_with_template(survey.df, template)
        
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if len(issues_df) > 0:
                issues_df.to_excel(out_path, index=False)
            else:
                pd.DataFrame(columns=['type', 'severity', 'column', 'row', 'value', 'message']).to_excel(out_path, index=False)
        
        error_count = len([i for i in issues if i['severity'] == 'error'])
        warning_count = len([i for i in issues if i['severity'] == 'warning'])
        
        return StepResult(
            success=True,
            input_row_count=len(survey.df),
            output_row_count=len(survey.df),
            modified_columns=[],
            affected_rows=len(set(i['row'] for i in issues if i['row'])),
            output_files=[str(output)] if output else [],
            messages=[
                f"模板检查: 模板 '{template.name}', 共发现 {len(issues)} 个异常",
                f"  错误: {error_count}, 警告: {warning_count}"
            ],
        )
    
    def _handle_sample_random(self, params: Dict[str, Any]) -> StepResult:
        """执行随机抽样"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        count = _get_param(params, 'count')
        ratio = _get_param(params, 'ratio')
        output = _get_param(params, 'output', 'output_survey_name') or f"{survey_id}_sample"
        seed = params.get('seed')
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df
        input_rows = len(df)
        
        if count is None and ratio is not None:
            count = max(1, int(input_rows * ratio))
        
        if count is None:
            count = max(1, int(input_rows * 0.1))
        
        n = min(count, input_rows)
        sampled_df = df.sample(n=n, random_state=seed)
        
        self._save_survey(SurveyData(
            name=output,
            df=sampled_df,
            source_path=survey.source_path,
            metadata={'sampled_from': survey_id, 'method': 'random', 'ratio': ratio, 'count': count},
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=len(sampled_df),
            modified_columns=[],
            affected_rows=len(sampled_df),
            messages=[f"随机抽样: {input_rows} -> {len(sampled_df)} 条，新问卷 '{output}'"],
        )
    
    def _handle_sample_stratified(self, params: Dict[str, Any]) -> StepResult:
        """执行分层抽样"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        column = _get_param(params, 'column', 'stratify_by')
        ratio = _get_param(params, 'ratio', 0.1)
        count = _get_param(params, 'count')
        output = _get_param(params, 'output', 'output_survey_name') or f"{survey_id}_stratified_{column}"
        seed = params.get('seed')
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df
        input_rows = len(df)
        
        if column not in df.columns:
            return StepResult(success=False, error=f"列不存在: {column}")
        
        sampled_parts = []
        for _, group in df.groupby(column):
            n = count or max(1, int(len(group) * ratio))
            n = min(n, len(group))
            sampled_parts.append(group.sample(n=n, random_state=seed))
        
        sampled_df = pd.concat(sampled_parts, ignore_index=True)
        
        self._save_survey(SurveyData(
            name=output,
            df=sampled_df,
            source_path=survey.source_path,
            metadata={'sampled_from': survey_id, 'stratify_by': column},
        ))
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=len(sampled_df),
            modified_columns=[],
            affected_rows=len(sampled_df),
            messages=[f"分层抽样: {input_rows} -> {len(sampled_df)} 条，新问卷 '{output}'"],
        )
    
    def _handle_export_survey(self, params: Dict[str, Any]) -> StepResult:
        """执行导出问卷"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        output = Path(_get_param(params, 'output', 'output_path'))
        format_type = params.get('format', 'xlsx')
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if format_type == 'xlsx' or output.suffix in ['.xlsx', '.xls']:
            survey.df.to_excel(output, index=False)
        else:
            survey.df.to_csv(output, index=False, encoding='utf-8-sig')
        
        return StepResult(
            success=True,
            input_row_count=len(survey.df),
            output_row_count=len(survey.df),
            modified_columns=[],
            affected_rows=len(survey.df),
            output_files=[str(output)],
            messages=[f"导出问卷 '{survey.name}' 到 {output} ({len(survey.df)} 行)"],
        )
    
    def _handle_export_logs(self, params: Dict[str, Any]) -> StepResult:
        """执行导出日志"""
        output = Path(_get_param(params, 'output', 'output_path'))
        verbose = params.get('verbose', False)
        
        output.parent.mkdir(parents=True, exist_ok=True)
        
        logs = []
        log_dir = self.workspace.root / 'logs'
        if log_dir.exists():
            log_files = sorted(log_dir.glob('*.json'))
            for lf in log_files:
                with open(lf, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
                    entry = {
                        'timestamp': log_data.get('timestamp', ''),
                        'command': log_data.get('command', ''),
                        'input_row_count': log_data.get('input_row_count', ''),
                        'output_row_count': log_data.get('output_row_count', ''),
                        'modified_columns': ', '.join(log_data.get('modified_columns', [])),
                        'affected_rows': log_data.get('affected_rows', ''),
                    }
                    if verbose:
                        entry['params'] = str(log_data.get('params', {}))
                        entry['input_files'] = ', '.join(log_data.get('input_files', []))
                        entry['output_files'] = ', '.join(log_data.get('output_files', []))
                        entry['changes'] = '; '.join(log_data.get('changes', []))
                    logs.append(entry)
        
        if logs:
            pd.DataFrame(logs).to_excel(output, index=False)
        else:
            columns = ['timestamp', 'command', 'input_row_count', 'output_row_count', 'modified_columns', 'affected_rows']
            if verbose:
                columns += ['params', 'input_files', 'output_files', 'changes']
            pd.DataFrame(columns=columns).to_excel(output, index=False)
        
        return StepResult(
            success=True,
            input_row_count=len(logs),
            output_row_count=len(logs),
            modified_columns=[],
            affected_rows=len(logs),
            output_files=[str(output)],
            messages=[f"导出处理日志 {len(logs)} 条到 {output}"],
        )
    
    def _handle_report_completion(self, params: Dict[str, Any]) -> StepResult:
        """生成完成率报告"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        output = Path(_get_param(params, 'output', 'output_path'))
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df
        input_rows = len(df)
        completion_data = []
        
        for col in df.columns:
            answered_mask = ~df[col].apply(is_empty)
            completion_rate = answered_mask.mean() if len(df) > 0 else 0
            completion_data.append({
                '问卷': survey.name,
                '题目': col,
                '总题数': len(df),
                '已答题数': int(answered_mask.sum()),
                '完成率': round(completion_rate, 4),
            })
        
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(completion_data).to_excel(output, index=False)
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[],
            affected_rows=input_rows,
            output_files=[str(output)],
            messages=[f"生成完成率报告: {len(completion_data)} 个字段"],
        )
    
    def _handle_report_anomalies(self, params: Dict[str, Any]) -> StepResult:
        """生成异常清单报告"""
        survey_id = _get_param(params, 'survey_id', 'survey_name')
        output = Path(_get_param(params, 'output', 'output_path'))
        numeric_only = params.get('numeric_only', False)
        zscore = params.get('zscore', 3.0)
        
        survey = self._get_survey(survey_id)
        if not survey:
            return StepResult(success=False, error=f"未找到问卷: {survey_id}")
        
        df = survey.df
        input_rows = len(df)
        anomalies = []
        
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
        
        output.parent.mkdir(parents=True, exist_ok=True)
        if anomalies:
            out_df = pd.DataFrame(anomalies, columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明'])
        else:
            out_df = pd.DataFrame(columns=['问卷名', '字段', '行号', '异常类型', '实际值', '说明'])
        
        if output.suffix in ['.xlsx', '.xls']:
            out_df.to_excel(output, index=False, engine='openpyxl')
        else:
            out_df.to_csv(output, index=False, encoding='utf-8-sig')
        
        return StepResult(
            success=True,
            input_row_count=input_rows,
            output_row_count=input_rows,
            modified_columns=[],
            affected_rows=len(set(a['行号'] for a in anomalies)),
            output_files=[str(output)],
            messages=[f"异常清单: {len(anomalies)} 个异常" if anomalies else "异常清单: 无异常"],
        )
