# AI 智能题库与在线刷题系统

一个完整可运行的题库管理 + 智能导入 + 在线刷题 + AI 学习助手平台。
后端 FastAPI + SQLAlchemy（SQLite/PostgreSQL），前端原生 SPA（无需构建），开箱即用。

## ✨ 核心功能

| 模块 | 能力 |
|---|---|
| 题库管理 | 多题库 CRUD、复制、章节、分类、搜索、共享（只读/可编辑）、公开/私有 |
| 智能导入 | 手动录入 / 文本批量粘贴 / 文件导入（TXT·CSV·Excel·Word·PDF）/ AI 辅助整理 |
| 题型识别 | 规则引擎（正则拆题+题型分类）+ AI 辅助 + 三层校验；支持单选/多选/判断/填空/简答/计算/未识别 |
| 去重 | 题干规范化 + SHA256 哈希 + 相似度检测（批内 + 跨库） |
| 刷题 | 顺序（从头开始·需手动选择）/ 随机 / 章节 / 专项 / 模拟考试 / 错题重练 / 收藏练习；**默认智能选题：未做 → 错题 → 已掌握**；答题卡、计时、断点续做 |
| 判题 | 客观题精确判分；填空支持等价表达；简答/计算 AI 辅助评分（强制标注"非绝对判定"） |
| 错题本 | 自动入册、连对自动升级掌握度（2 次→基本掌握、3 次→已掌握、答错清零）、间隔复习（1/2/4/7/15/30 天）、错题分析 |
| AI 助教 | 题目解析、互动答疑（多轮）、提示模式（不泄露答案）、生成相似题（草稿区）、错题分析 |
| 学习桌宠 | 右下角悬浮猫头鹰桌宠：可拖动、闲置鼓励语、答对庆祝/答错打气、成绩反应、一键呼出 AI 对话 |
| 统计 | 正确率、题型/知识点掌握、每日趋势、错题分析（全部来自真实数据库） |
| 多用户 | 注册登录（JWT）、数据隔离、管理员角色、共享题库学习记录互不覆盖；登录/注册/失败事件全部入库（`login_records` 表），设置页可查登录历史 |

## 🚀 快速启动

### 环境要求
- Python 3.10+

### 一键启动

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # 按需修改配置
python -m uvicorn app.main:app --host 0.0.0.0 --port 8017
```

Windows（PowerShell / cmd）可直接双击 `start.bat`，或在 Git Bash 中执行 `bash start.sh`。

浏览器打开 **http://127.0.0.1:8017** 即可使用。
第一个注册的用户自动成为管理员（可配置 AI API）。

### 运行测试

```bash
cd backend
python -m pytest tests/ -q         # 30 项单元 + API 测试
python tests/e2e_test.py           # 55 项全链路验收（需先启动服务）
```

## ⚙️ 配置

配置文件：`backend/.env`（参考 `.env.example`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `SECRET_KEY` | JWT 密钥（生产必改） | dev 默认值 |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./quiz_platform.db` |
| `AI_API_BASE` | OpenAI 兼容 API 地址 | `https://api.openai.com/v1` |
| `AI_API_KEY` | 模型 API Key（也可在系统设置页配置，安全存服务端） | 空 |
| `AI_MODEL` | 模型名称 | `gpt-4o-mini` |
| `AI_TIMEOUT` / `AI_MAX_TOKENS` | 超时与输出上限 | 60 / 2048 |

**AI 未配置时**：所有 AI 功能返回明确标记的「开发占位 · 非真实模型回答」内容，
刷题、判题、错题本等核心功能完全不受影响。绝不会把占位内容伪装成真实 AI 生成。

### 切换 PostgreSQL

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/quizdb python -m uvicorn app.main:app
```

## 📁 项目结构

```
quiz-platform/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口（含 SPA 静态托管）
│   │   ├── config.py          # 环境配置
│   │   ├── database.py        # SQLAlchemy 连接
│   │   ├── models.py          # 13 张数据表
│   │   ├── schemas.py         # Pydantic 模型
│   │   ├── security.py        # JWT / bcrypt
│   │   ├── deps.py            # 权限依赖注入
│   │   ├── routers/           # auth/banks/questions/importer/practice/ai/stats
│   │   ├── services/
│   │   │   ├── parser.py      # 题目拆分 + 题型识别 + 答案提取（规则层）
│   │   │   ├── grader.py      # 判题引擎
│   │   │   ├── ai_client.py   # OpenAI 兼容客户端 + AI 业务封装
│   │   │   ├── file_import.py # TXT/CSV/Excel/Word/PDF 解析（OCR 扩展点）
│   │   │   └── dedup.py       # 哈希 + 相似度去重
│   │   └── static/            # 前端 SPA（index.html + css + js）
│   ├── tests/                 # pytest 单元/API 测试 + e2e 验收脚本
│   ├── requirements.txt
│   └── .env.example
├── start.sh / start.bat       # 启动脚本
└── README.md
```

## 🧪 测试说明

| 文件 | 覆盖 | 用例数 |
|---|---|---|
| `tests/test_parser_grader.py` | 题目拆分、单选/多选/判断/填空识别、答案格式（ABC / A,B,C / A、B、C）、答案校验、重复检测、判题引擎 | 21 |
| `tests/test_api.py` | 权限控制（私有/共享/只读/管理员/未登录）、重复导入跳过、答题记录持久化、多用户数据隔离、登录记录入库、智能选题优先级 | 15 |
| `tests/e2e_test.py` | 55 项全链路验收：注册→建库→导入识别→确认→刷题判题→错题→收藏→考试→AI 降级→隔离→共享→统计→文件导入→去重 | 55 |

> 测试使用独立数据库（`tests/conftest.py` 强制 `tests/pytest_quiz.db`），**不会覆盖正式数据** `quiz_platform.db`。

重点验证（对应验收要求）：
1. 题目拆分（多题号/括号题号/无题号空行分隔）
2. 单选与多选识别（含"4 个选项 ≠ 单选"规则）
3. 答案校验（答案与选项匹配、缺答案标记待确认、AI 不覆盖原始答案）
4. 重复导入（哈希 + 相似度，跳过计数）
5. 权限控制（私有隔离 / 共享只读 / 管理员接口）
6. 答题记录持久化（刷新后仍在，跨用户隔离）

## 📖 核心链路演示

创建题库 → 导入题目（粘贴文本自动拆分识别）→ 逐题预览/编辑 → 确认保存 →
生成练习 → 作答判题 → AI 解析 → 自动进错题本

粘贴示例（在「智能导入」页）：

```
1. 计算机的 CPU 主要负责什么？
A. 存储数据
B. 执行指令
C. 显示画面
D. 连接网络
答案：B

2. 以下哪些属于操作系统？
A. Windows
B. Linux
C. MySQL
D. macOS
答案：ABD

3. FIFO 是先进先出算法。
答案：正确
```

## 🔌 AI 能力接入

1. 用管理员账号登录 → 「系统设置」→「AI 服务配置」
2. 填入 OpenAI 兼容 API 地址 / 模型名 / API Key → 保存（Key 仅存服务端）
3. 点击「测试连接」确认可用
4. 刷题页右侧「AI 助教」即可题目解析、互动答疑、提示模式
5. 「AI 生成相似题」先进草稿区，人工确认后入库

支持任意 OpenAI 兼容服务商（OpenAI / DeepSeek / Moonshot / 本地 vLLM 等）。

## ⚠️ 已知边界（明确标注，非隐藏缺陷）

- 扫描版 PDF：无 OCR 引擎，会提示先转文本（`services/file_import.py` 留有 OCR 扩展点）
- `.xls` 旧格式不支持，请另存 `.xlsx` / `.csv`
- 简答/计算题判分：无 AI 时为启发式/人工待评，不会伪造判定
- AI 生成题目强制进入 `is_draft` 草稿态，需人工确认才入正式库

## 📄 License

MIT
