"""题目模板/变量字典处理"""
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class VariableDefinition:
    """变量定义"""
    name: str
    required: bool = False
    type: str = 'string'  # string, number, integer, boolean, date
    options: Optional[List[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ''
    category: str = ''


@dataclass
class Template:
    """题目模板"""
    name: str
    version: str = '1.0'
    description: str = ''
    variables: List[VariableDefinition] = field(default_factory=list)
    
    def get_variable(self, name: str) -> Optional[VariableDefinition]:
        for v in self.variables:
            if v.name == name:
                return v
        return None
    
    def variable_names(self) -> List[str]:
        return [v.name for v in self.variables]


def load_template(template_path: Path) -> Template:
    """加载模板文件（支持 JSON 或 CSV）"""
    template_path = Path(template_path)
    
    if template_path.suffix.lower() == '.json':
        return _load_json_template(template_path)
    elif template_path.suffix.lower() == '.csv':
        return _load_csv_template(template_path)
    else:
        raise ValueError(f"不支持的模板格式: {template_path.suffix}")


def _load_json_template(template_path: Path) -> Template:
    """从 JSON 加载模板"""
    with open(template_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    variables = []
    for var_data in data.get('variables', []):
        var = VariableDefinition(
            name=var_data['name'],
            required=var_data.get('required', False),
            type=var_data.get('type', 'string'),
            options=var_data.get('options'),
            min_value=var_data.get('min'),
            max_value=var_data.get('max'),
            description=var_data.get('description', ''),
            category=var_data.get('category', ''),
        )
        variables.append(var)
    
    return Template(
        name=data.get('name', template_path.stem),
        version=data.get('version', '1.0'),
        description=data.get('description', ''),
        variables=variables,
    )


def _load_csv_template(template_path: Path) -> Template:
    """从 CSV 加载模板"""
    df = pd.read_csv(template_path, encoding='utf-8-sig')
    
    required_cols = {'name'}
    if not required_cols.issubset(set(df.columns.str.lower())):
        raise ValueError(f"CSV模板必须包含 name 列")
    
    col_map = {c.lower(): c for c in df.columns}
    
    variables = []
    for _, row in df.iterrows():
        name = str(row[col_map.get('name', 'name')]).strip()
        if not name:
            continue
        
        options = None
        if 'options' in col_map:
            opt_str = str(row[col_map['options']]).strip()
            if opt_str and opt_str.lower() not in ['nan', 'none', '']:
                options = [o.strip() for o in opt_str.split('|')]
        
        min_val = None
        if 'min' in col_map:
            try:
                min_val = float(row[col_map['min']])
            except (ValueError, TypeError):
                pass
        
        max_val = None
        if 'max' in col_map:
            try:
                max_val = float(row[col_map['max']])
            except (ValueError, TypeError):
                pass
        
        var = VariableDefinition(
            name=name,
            required=str(row.get(col_map.get('required', 'required'), '')).strip().lower() in ['true', '1', 'yes', '是'],
            type=str(row.get(col_map.get('type', 'type'), 'string')).strip().lower() or 'string',
            options=options,
            min_value=min_val,
            max_value=max_val,
            description=str(row.get(col_map.get('description', 'description'), '')).strip(),
            category=str(row.get(col_map.get('category', 'category'), '')).strip(),
        )
        variables.append(var)
    
    return Template(
        name=template_path.stem,
        variables=variables,
    )


def validate_with_template(df: pd.DataFrame, template: Template) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """使用模板验证数据
    
    返回: (异常列表, 异常明细DataFrame)
    """
    issues = []
    
    template_cols = template.variable_names()
    data_cols = list(df.columns)
    
    missing_columns = [c for c in template_cols if c not in data_cols]
    for col in missing_columns:
        var = template.get_variable(col)
        issues.append({
            'type': 'missing_column',
            'severity': 'error' if var and var.required else 'warning',
            'column': col,
            'row': None,
            'value': None,
            'message': f"缺少预期列: {col}{' (必填)' if var and var.required else ''}",
        })
    
    extra_columns = [c for c in data_cols if c not in template_cols]
    for col in extra_columns:
        issues.append({
            'type': 'extra_column',
            'severity': 'info',
            'column': col,
            'row': None,
            'value': None,
            'message': f"存在额外列: {col}",
        })
    
    for var in template.variables:
        if var.name not in data_cols:
            continue
        
        col_data = df[var.name]
        
        if var.required:
            missing_mask = col_data.isna()
            missing_rows = [i + 2 for i, is_missing in enumerate(missing_mask) if is_missing]
            for row in missing_rows:
                issues.append({
                    'type': 'required_missing',
                    'severity': 'error',
                    'column': var.name,
                    'row': row,
                    'value': None,
                    'message': f"必填项缺失: {var.name}",
                })
        
        if var.options:
            valid_values = set(str(o).strip() for o in var.options)
            valid_values_num = set()
            for o in var.options:
                try:
                    valid_values_num.add(float(o))
                except (ValueError, TypeError):
                    pass
            
            for idx, val in enumerate(col_data):
                if pd.isna(val):
                    continue
                
                val_str = str(val).strip()
                val_num = None
                try:
                    val_num = float(val)
                except (ValueError, TypeError):
                    pass
                
                is_valid = (val_str in valid_values) or (val_num is not None and val_num in valid_values_num)
                if not is_valid:
                    issues.append({
                        'type': 'invalid_option',
                        'severity': 'error',
                        'column': var.name,
                        'row': idx + 2,
                        'value': val_str,
                        'message': f"选项越界: {val_str}，允许值: {', '.join(var.options)}",
                    })
        
        if var.type in ['number', 'integer']:
            for idx, val in enumerate(col_data):
                if pd.isna(val):
                    continue
                
                try:
                    num_val = float(val)
                except (ValueError, TypeError):
                    issues.append({
                        'type': 'type_mismatch',
                        'severity': 'error',
                        'column': var.name,
                        'row': idx + 2,
                        'value': str(val),
                        'message': f"类型不匹配: 应为{var.type}，实际值: {val}",
                    })
                    continue
                
                if var.min_value is not None and num_val < var.min_value:
                    issues.append({
                        'type': 'value_out_of_range',
                        'severity': 'error',
                        'column': var.name,
                        'row': idx + 2,
                        'value': num_val,
                        'message': f"数值越界: {num_val} < 最小值 {var.min_value}",
                    })
                
                if var.max_value is not None and num_val > var.max_value:
                    issues.append({
                        'type': 'value_out_of_range',
                        'severity': 'error',
                        'column': var.name,
                        'row': idx + 2,
                        'value': num_val,
                        'message': f"数值越界: {num_val} > 最大值 {var.max_value}",
                    })
    
    issues_df = pd.DataFrame(issues) if issues else pd.DataFrame(
        columns=['type', 'severity', 'column', 'row', 'value', 'message']
    )
    
    return issues, issues_df
