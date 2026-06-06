"""数据模型定义"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import pandas as pd


@dataclass
class SurveyData:
    """问卷数据"""
    name: str
    df: pd.DataFrame
    source_path: Path
    sheet_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    round_num: Optional[int] = None

    @property
    def columns(self) -> List[str]:
        return list(self.df.columns)

    @property
    def row_count(self) -> int:
        return len(self.df)


@dataclass
class InterviewData:
    """访谈数据"""
    name: str
    content: str
    source_path: Path
    speaker_labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """检查结果"""
    check_type: str
    passed: bool
    issues: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""


@dataclass
class ProcessLog:
    """处理日志"""
    timestamp: str
    command: str
    params: Dict[str, Any]
    input_files: List[str]
    output_files: List[str]
    changes: List[str]
