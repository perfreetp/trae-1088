# SurveyKit - 高校课题组问卷访谈资料整理工具

一个功能完整的命令行工具，专为高校课题组设计，用于高效处理批量问卷和访谈资料。

## 功能特性

### 8 组核心命令

| 命令组 | 功能 | 子命令 |
|--------|------|--------|
| **import** | 导入表格和文本目录 | `table` / `interview` / `dir` |
| **check** | 数据质量检查 | `missing` / `options` / `duplicate` / `all` |
| **clean** | 数据清洗 | `date` / `region` / `rename` / `whitespace` |
| **merge** | 合并与拆分 | `surveys` / `split-interview` |
| **sample** | 抽样 | `random` / `stratified` / `systematic` |
| **mask** | 脱敏处理 | `name` / `phone` / `idcard` / `all` |
| **export** | 导出 | `survey` / `interview` / `all` / `logs` |
| **report** | 统计报告 | `completion` / `anomalies` / `summary` |

### 主要功能

- ✅ 批量导入 Excel/CSV 表格和访谈文本
- ✅ 检查缺失题目、选项越界、重复受访者
- ✅ 统一日期和地区名称写法
- ✅ 批量重命名附件文件
- ✅ 合并多轮问卷数据
- ✅ 拆分访谈逐字稿按说话人
- ✅ 随机抽样、分层抽样、系统抽样
- ✅ 姓名、电话、身份证号脱敏
- ✅ 统计题目完成率、生成异常清单
- ✅ 导出 Excel/CSV/JSON 多种格式
- ✅ 完整处理日志记录
- ✅ 预览模式（--preview）不修改原文件

## 安装

### 方式一：源码安装（推荐）

```bash
# 克隆或下载源码
cd surveykit

# 安装依赖
pip install -r requirements.txt

# 安装为可执行命令
pip install -e .
```

### 方式二：直接运行

```bash
pip install -r requirements.txt
python -m surveykit.cli --help
```

## 快速开始

### 1. 查看帮助

```bash
surveykit --help
surveykit import --help
surveykit check missing --help
```

### 2. 导入数据

```bash
# 导入单个 Excel 文件
surveykit import table data/questionnaire.xlsx

# 导入整个目录（包括表格和访谈）
surveykit import dir ./raw_data --round 1
```

### 3. 检查数据质量

```bash
# 检查缺失值
surveykit check missing questionnaire1

# 检查选项是否越界
surveykit check options questionnaire1 -c 性别 -v 男,女,其他

# 检查重复受访者
surveykit check duplicate questionnaire1 -c 学号,姓名
```

### 4. 数据清洗

```bash
# 统一日期格式
surveykit clean date questionnaire1 -c 填写日期

# 统一地区名称
surveykit clean region questionnaire1 -c 所在省份

# 预览模式（不修改原文件）
surveykit --preview clean date questionnaire1 -c 填写日期
```

### 5. 抽样

```bash
# 随机抽样 100 份
surveykit sample random questionnaire1 -n 100 --seed 42

# 按性别分层抽样
surveykit sample stratified questionnaire1 -c 性别 -r 0.2
```

### 6. 脱敏处理

```bash
# 一键脱敏所有敏感字段
surveykit mask all questionnaire1

# 分别脱敏
surveykit mask name questionnaire1 -c 姓名
surveykit mask phone questionnaire1 -c 联系电话
```

### 7. 生成报告

```bash
# 题目完成率统计
surveykit report completion -o reports/completion.xlsx

# 异常数据清单
surveykit report anomalies questionnaire1 -o reports/issues.json

# 数据汇总
surveykit report summary -o reports/summary.json
```

### 8. 导出结果

```bash
# 导出单个问卷
surveykit export survey questionnaire1 -o output/cleaned.xlsx

# 批量导出全部
surveykit export all ./output --format xlsx

# 导出处理日志
surveykit export logs -o logs/history.json
```

## 工作区结构

工具会在当前目录创建 `.surveykit` 工作区：

```
.surveykit/
├── surveys/       # 问卷数据 (parquet格式)
├── interviews/    # 访谈文本
├── exports/       # 导出文件
├── reports/       # 报告文件
├── logs/          # 处理日志
├── config/        # 配置文件
└── index.json     # 数据索引
```

## 常用工作流示例

### 完整数据处理流程

```bash
# 1. 导入原始数据
surveykit import dir ./raw_data --round 1

# 2. 查看工作区状态
surveykit status

# 3. 质量检查
surveykit check all

# 4. 清洗数据
surveykit clean date round1_survey -c 提交时间
surveykit clean region round1_survey -c 省份
surveykit clean whitespace round1_survey

# 5. 脱敏
surveykit mask all round1_survey

# 6. 生成报告
surveykit report completion round1_survey -o reports/completion.xlsx
surveykit report anomalies round1_survey -o reports/anomalies.xlsx

# 7. 导出
surveykit export all ./deliverables --format xlsx
```

### 多轮问卷合并

```bash
surveykit import table round1.xlsx --round 1
surveykit import table round2.xlsx --round 2
surveykit merge surveys round1 round2 -o merged -k 学号
surveykit export survey merged -o final/merged_survey.xlsx
```

### 访谈拆分

```bash
surveykit import interview interviews/
surveykit merge split-interview interview_001 -o output/split
```

## 命令详解

### import table

| 参数 | 说明 |
|------|------|
| `path` | 文件或目录路径 |
| `--sheet/-s` | Excel 工作表名 |
| `--name/-n` | 问卷名称 |
| `--round` | 问卷轮次 |
| `--encoding/-e` | CSV 编码 |

### check options

| 参数 | 说明 |
|------|------|
| `survey_id` | 问卷 ID |
| `--column/-c` | 要检查的列名 |
| `--valid/-v` | 有效选项，逗号分隔 |

### sample stratified

| 参数 | 说明 |
|------|------|
| `--column/-c` | 分层列名 |
| `--ratio/-r` | 抽样比例 (0-1) |
| `--count/-n` | 每层抽样数量 |
| `--seed` | 随机种子 |

## 许可证

MIT License
