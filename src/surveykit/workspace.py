"""工作区管理"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import SurveyData, InterviewData, ProcessLog
from .utils import save_json, load_json


class Workspace:
    """工作区管理器"""
    
    def __init__(self, root_path: Optional[Path] = None):
        self.root = Path(root_path or Path.cwd() / '.surveykit')
        self.root.mkdir(parents=True, exist_ok=True)
        self._init_dirs()
        self._load_index()
    
    def _init_dirs(self) -> None:
        """初始化目录结构"""
        dirs = ['surveys', 'interviews', 'exports', 'reports', 'logs', 'tmp', 'config']
        for d in dirs:
            (self.root / d).mkdir(parents=True, exist_ok=True)
    
    def _load_index(self) -> None:
        """加载索引文件"""
        self.index_path = self.root / 'index.json'
        if self.index_path.exists():
            self.index = load_json(self.index_path)
        else:
            self.index = {
                'surveys': {},
                'interviews': {},
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
    
    def _save_index(self) -> None:
        """保存索引文件"""
        self.index['updated_at'] = datetime.now().isoformat()
        save_json(self.index, self.index_path)
    
    def add_survey(self, survey: SurveyData) -> str:
        """添加问卷数据"""
        survey_id = survey.name
        save_path = self.root / 'surveys' / f'{survey_id}.parquet'
        survey.df.to_parquet(save_path)
        
        self.index['surveys'][survey_id] = {
            'name': survey.name,
            'source_path': str(survey.source_path),
            'sheet_name': survey.sheet_name,
            'parquet_path': str(save_path),
            'row_count': survey.row_count,
            'columns': survey.columns,
            'round_num': survey.round_num,
            'metadata': survey.metadata,
            'added_at': datetime.now().isoformat(),
        }
        self._save_index()
        return survey_id
    
    def get_survey(self, survey_id: str) -> Optional[SurveyData]:
        """获取问卷数据"""
        import pandas as pd
        
        if survey_id not in self.index['surveys']:
            return None
        
        info = self.index['surveys'][survey_id]
        parquet_path = Path(info['parquet_path'])
        if not parquet_path.exists():
            return None
        
        df = pd.read_parquet(parquet_path)
        return SurveyData(
            name=info['name'],
            df=df,
            source_path=Path(info['source_path']),
            sheet_name=info.get('sheet_name'),
            metadata=info.get('metadata', {}),
            round_num=info.get('round_num'),
        )
    
    def list_surveys(self) -> List[Dict[str, Any]]:
        """列出所有问卷"""
        return list(self.index['surveys'].values())
    
    def add_interview(self, interview: InterviewData) -> str:
        """添加访谈数据"""
        interview_id = interview.name
        save_path = self.root / 'interviews' / f'{interview_id}.txt'
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(interview.content)
        
        self.index['interviews'][interview_id] = {
            'name': interview.name,
            'source_path': str(interview.source_path),
            'text_path': str(save_path),
            'speaker_labels': interview.speaker_labels,
            'metadata': interview.metadata,
            'added_at': datetime.now().isoformat(),
        }
        self._save_index()
        return interview_id
    
    def get_interview(self, interview_id: str) -> Optional[InterviewData]:
        """获取访谈数据"""
        if interview_id not in self.index['interviews']:
            return None
        
        info = self.index['interviews'][interview_id]
        text_path = Path(info['text_path'])
        if not text_path.exists():
            return None
        
        with open(text_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return InterviewData(
            name=info['name'],
            content=content,
            source_path=Path(info['source_path']),
            speaker_labels=info.get('speaker_labels', {}),
            metadata=info.get('metadata', {}),
        )
    
    def list_interviews(self) -> List[Dict[str, Any]]:
        """列出所有访谈"""
        return list(self.index['interviews'].values())
    
    def add_log(self, log: ProcessLog) -> None:
        """添加处理日志"""
        log_path = self.root / 'logs' / f'{log.timestamp}_{log.command}.json'
        save_json({
            'timestamp': log.timestamp,
            'command': log.command,
            'params': log.params,
            'input_files': log.input_files,
            'output_files': log.output_files,
            'changes': log.changes,
        }, log_path)
    
    def get_export_path(self, filename: str) -> Path:
        """获取导出文件路径"""
        path = self.root / 'exports' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_report_path(self, filename: str) -> Path:
        """获取报告文件路径"""
        path = self.root / 'reports' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_tmp_path(self, filename: str) -> Path:
        """获取临时文件路径"""
        path = self.root / 'tmp' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    
    def save_config(self, name: str, config: Dict[str, Any]) -> None:
        """保存配置"""
        save_json(config, self.root / 'config' / f'{name}.json')
    
    def load_config(self, name: str) -> Optional[Dict[str, Any]]:
        """加载配置"""
        config_path = self.root / 'config' / f'{name}.json'
        if config_path.exists():
            return load_json(config_path)
        return None
    
    def clear_tmp(self) -> None:
        """清理临时文件"""
        tmp_dir = self.root / 'tmp'
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True, exist_ok=True)
