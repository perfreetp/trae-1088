"""通用工具函数"""
import re
import csv
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import chardet


def detect_encoding(file_path: Path) -> str:
    """检测文件编码"""
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read(100000))
    return result.get('encoding', 'utf-8')


def read_text_file(file_path: Path) -> str:
    """读取文本文件，自动检测编码"""
    encoding = detect_encoding(file_path)
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()
    except (UnicodeDecodeError, TypeError):
        for enc in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法读取文件: {file_path}")


def generate_id(*args: str) -> str:
    """生成唯一ID"""
    content = "|".join(str(a) for a in args)
    return hashlib.md5(content.encode()).hexdigest()[:12]


def is_empty(value: Any) -> bool:
    """判断值是否为空（None、NaN、空字符串、空格）"""
    import pandas as pd
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, pd.Series):
        return value.isna().all()
    if isinstance(value, str) and value.strip() == '':
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


def normalize_date(date_str: Any) -> Any:
    """统一日期格式为 YYYY-MM-DD，空值保持为空字符串"""
    if is_empty(date_str):
        return ''
    
    date_str = str(date_str).strip()
    if date_str.lower() in ['nan', 'nat', 'none', 'null', '']:
        return ''
    
    patterns = [
        (r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', r'\1-\2-\3'),
        (r'(\d{4})(\d{2})(\d{2})', r'\1-\2-\3'),
        (r'(\d{1,2})[-/月.](\d{1,2})[-/年.](\d{4})', r'\3-\1-\2'),
    ]
    
    for pattern, repl in patterns:
        match = re.match(pattern, date_str)
        if match:
            try:
                year, month, day = map(int, match.groups())
                dt = datetime(year, month, day)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
    
    from dateutil import parser
    try:
        dt = parser.parse(date_str, fuzzy=True)
        return dt.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return date_str


def normalize_region(region_str: Any, region_map: Optional[Dict[str, str]] = None) -> Any:
    """统一地区名称写法，空值保持为空字符串"""
    if is_empty(region_str):
        return ''
    
    region_str = str(region_str).strip()
    if region_str.lower() in ['nan', 'nat', 'none', 'null', '']:
        return ''
    
    default_map = {
        '北京': '北京市', '北京市': '北京市', '京': '北京市',
        '上海': '上海市', '上海市': '上海市', '沪': '上海市',
        '天津': '天津市', '天津市': '天津市', '津': '天津市',
        '重庆': '重庆市', '重庆市': '重庆市', '渝': '重庆市',
        '广东': '广东省', '广东省': '广东省', '粤': '广东省',
        '江苏': '江苏省', '江苏省': '江苏省', '苏': '江苏省',
        '浙江': '浙江省', '浙江省': '浙江省', '浙': '浙江省',
        '山东': '山东省', '山东省': '山东省', '鲁': '山东省',
        '河南': '河南省', '河南省': '河南省', '豫': '河南省',
        '四川': '四川省', '四川省': '四川省', '川': '四川省', '蜀': '四川省',
        '湖北': '湖北省', '湖北省': '湖北省', '鄂': '湖北省',
        '湖南': '湖南省', '湖南省': '湖南省', '湘': '湖南省',
        '福建': '福建省', '福建省': '福建省', '闽': '福建省',
        '安徽': '安徽省', '安徽省': '安徽省', '皖': '安徽省',
        '河北': '河北省', '河北省': '河北省', '冀': '河北省',
        '陕西': '陕西省', '陕西省': '陕西省', '陕': '陕西省', '秦': '陕西省',
        '山西': '山西省', '山西省': '山西省', '晋': '山西省',
        '辽宁': '辽宁省', '辽宁省': '辽宁省', '辽': '辽宁省',
        '吉林': '吉林省', '吉林省': '吉林省', '吉': '吉林省',
        '黑龙江': '黑龙江省', '黑龙江省': '黑龙江省', '黑': '黑龙江省',
        '云南': '云南省', '云南省': '云南省', '云': '云南省', '滇': '云南省',
        '贵州': '贵州省', '贵州省': '贵州省', '贵': '贵州省', '黔': '贵州省',
        '甘肃': '甘肃省', '甘肃省': '甘肃省', '甘': '甘肃省', '陇': '甘肃省',
        '青海': '青海省', '青海省': '青海省', '青': '青海省',
        '海南': '海南省', '海南省': '海南省', '琼': '海南省',
        '台湾': '台湾省', '台湾省': '台湾省', '台': '台湾省',
        '内蒙古': '内蒙古自治区', '内蒙古自治区': '内蒙古自治区',
        '广西': '广西壮族自治区', '广西壮族自治区': '广西壮族自治区',
        '西藏': '西藏自治区', '西藏自治区': '西藏自治区',
        '宁夏': '宁夏回族自治区', '宁夏回族自治区': '宁夏回族自治区',
        '新疆': '新疆维吾尔自治区', '新疆维吾尔自治区': '新疆维吾尔自治区',
        '香港': '香港特别行政区', '香港特别行政区': '香港特别行政区',
        '澳门': '澳门特别行政区', '澳门特别行政区': '澳门特别行政区',
    }
    
    if region_map:
        default_map.update(region_map)
    
    return default_map.get(region_str, region_str)


def mask_name(name: Any) -> Any:
    """姓名脱敏：保留姓氏，其余用*代替，空值保持为空字符串"""
    if is_empty(name):
        return ''
    
    name = str(name).strip()
    if name.lower() in ['nan', 'nat', 'none', 'null', '']:
        return ''
    
    if len(name) == 1:
        return name
    if len(name) == 2:
        return name[0] + '*'
    return name[0] + '*' * (len(name) - 1)


def mask_phone(phone: Any) -> Any:
    """手机号脱敏：中间4位用*代替，空值保持为空字符串"""
    if is_empty(phone):
        return ''
    
    phone = str(phone).strip()
    if phone.lower() in ['nan', 'nat', 'none', 'null', '']:
        return ''
    
    phone = re.sub(r'\D', '', phone)
    if len(phone) == 11:
        return phone[:3] + '****' + phone[-4:]
    return phone[:2] + '*' * max(0, len(phone) - 4) + phone[-2:] if len(phone) > 4 else '****'


def mask_id_card(id_card: Any) -> Any:
    """身份证号脱敏，空值保持为空字符串"""
    if is_empty(id_card):
        return ''
    
    id_card = str(id_card).strip()
    if id_card.lower() in ['nan', 'nat', 'none', 'null', '']:
        return ''
    if len(id_card) >= 10:
        return id_card[:6] + '*' * (len(id_card) - 10) + id_card[-4:]
    return '*' * len(id_card)


def get_file_list(directory: Path, extensions: Optional[List[str]] = None) -> List[Path]:
    """获取目录下指定扩展名的文件列表"""
    if not directory.exists():
        return []
    
    files = []
    for f in directory.rglob('*'):
        if f.is_file():
            if extensions:
                if f.suffix.lower() in [e.lower() for e in extensions]:
                    files.append(f)
            else:
                files.append(f)
    return sorted(files)


def save_json(data: Any, file_path: Path) -> None:
    """保存JSON文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(file_path: Path) -> Any:
    """加载JSON文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def safe_filename(filename: str) -> str:
    """生成安全的文件名"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)
