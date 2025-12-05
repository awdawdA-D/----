# 政企智能舆情分析报告生成智能体应用系统

面向政企场景的舆情数据采集、清洗、分析与报告生成应用。系统集成了多源新闻采集、基于大模型的分析与清洗、可配置的抽取规则，以及管理后台。

## 主要特性
- AI 引擎管理：支持配置多家服务商的模型参数（`provider`/`api_base`/`api_key`/`model_name`/`persona`），内置连接与生成功能测试。
- AI 数据清洗与分析：通过已配置的大模型，对 `collection_records` 表进行查询、分析与清洗；结果保存到 `ai_analysis_results` 并提供历史查看。
- 多源新闻采集：内置百度、新华、（可扩展）新浪/凤凰等来源采集，支持批量与流式采集，并进行基础数据清洗与去重。
- 可配置抽取规则：针对详情页可配置 XPath/CSS 选择器与请求头，自动抽取标题与正文。
- 管理后台：用户与角色、系统设置、采集器管理、规则管理、AI 引擎与分析 DEMO。

## 目录结构（关键文件）
- `project/app/__init__.py`：Flask 应用工厂与数据库初始化（含自动迁移逻辑）
- `project/app/models.py`：数据库模型定义
- `project/app/admin.py`：管理后台路由与核心业务逻辑（AI 引擎、分析 DEMO、采集器、规则等）
- `project/app/crawler.py`：多源采集与清洗实现
- `project/templates/`：前端模板（Layui 风格管理后台）
- `project/app.db`：SQLite 数据库（默认文件路径）

## 数据库模型
- `collection_records`：舆情采集数据表
  - `id, keyword, title, summary, source, original_url, cover, deep_collected, deep_content, created_at`
- `ai_engines`：AI 引擎配置表
  - `id, provider, api_base, api_key, model_name, persona, created_at`
- `ai_analysis_results`：AI 分析结果表
  - `id, engine_id, ai_model_name, instruction, result_text, created_at`
- 其他：`users, roles, system_settings, collection_rules, crawler_sources`

> 首次启动会自动创建并迁移数据库表结构；当检测到 `ai_engines` 缺少 `persona` 字段时，会自动执行 `ALTER TABLE ai_engines ADD COLUMN persona TEXT`。

## 快速开始
1. 安装依赖（示例）：
   - `pip install flask flask_sqlalchemy sqlalchemy flask_login requests beautifulsoup4 lxml charset-normalizer`
2. 进入仓库目录并启动：
   - PowerShell：
     - `setx FLASK_APP project.app`
     - `setx FLASK_ENV development`
     - `flask run`
   - 或：
     - `python -c "from project.app import create_app; app = create_app(); app.run(host='0.0.0.0', port=5000, debug=True)"`
3. 访问管理后台：
   - `http://localhost:5000/admin`
   - 默认管理员：用户名 `admin`，密码 `123456`

## 功能与用法

### AI 引擎管理（/admin/ai_engines）
- 新增/编辑引擎参数：`provider`、`api_base`、`api_key`、`model_name`、`persona`
- 测试：调用 `/chat/completions` 做最小生成能力测试
- 设为默认：将当前引擎信息写入本地存储，便于前端 DEMO 默认选用

示例（SiliconFlow - Qwen3-30B-A3B-Instruct-2507）：
- `API地址`：`https://api.siliconflow.cn/v1`
- `API密钥`：在平台申请的 Bearer 密钥
- `模型名称`：`Qwen/Qwen3-30B-A3B-Instruct-2507`
- `人设`：可设置你期望的视角与语气，例如：
  - 你是一名坚定的马克思主义者，你熟读马列毛著作，你深知世界上没有任何一种能够用来衡量万物的尺度，你坚信，任何一种事物都具有正反面，必须要用动态的发展的全面的眼光看待事物，既不盲目赞美，也不全盘否定，你时刻也心存宽容

> 人设通过系统提示自动注入到所有 LLM 调用路径（普通对话、JSON 回复、工具调用），确保输出风格一致。

### AI 数据清洗与分析 DEMO（/admin/ai_clean_demo）
- 选择引擎与输入分析指令，系统将：
  - 构造系统提示并可选注入人设
  - 调用 LLM 对 `collection_records` 进行查询与分析（工具调用）或总结输出
  - 将结果文本保存到 `ai_analysis_results`
- 历史分析（按钮）：读取 `ai_analysis_results` 最近记录并展示，支持长文“展开/收起”

工具定义（供 LLM 使用）：
- `get_table_schema()`：返回 `collection_records` 字段信息
- `select_collection_records({ keyword?, days?, limit })`：支持关键词模糊、近几天过滤与条数限制

### 新闻采集与流式展示（/admin/collector）
- 批量采集：从来源（如 `baidu`/`xinhua` 等）获取列表数据
- 流式采集：`/admin/collector/stream` 以 SSE 方式边采边播，便于前端实时展示进度
- 清洗规范：统一去除零宽字符、规范空白、去重标题、校验 URL/封面地址、兜底封面

### 抽取规则管理（/admin/rules）
- 针对详情页配置：标题 XPath、正文 XPath、请求头（文本自动规范化）
- 内置通用抽取回退：在规则失效时尽可能提取页面主体内容

### 其他管理
- 用户与角色（/admin/users）：内置 `admin/user` 角色；默认管理员账号初始化
- 系统设置（/admin/settings）：应用名称等基础配置

## 注意事项
- API 密钥在界面中以掩码展示，避免外泄；请求时通过 `Authorization: Bearer XXX` 与 `x-api-key: XXX`
- 超时与生成长度：LLM 请求默认 `timeout=(10,60)`、`max_tokens=512`；可根据服务商限制调整
- 数据库文件默认纳入版本管理，如不希望跟踪可配置 `.gitignore` 并移除 `project/app.db` 的跟踪

## 常见问题
- 测试通过但 DEMO 无输出：通常为超时或模型返回空；已在后端做错误预览与提示，并提高了超时与 `max_tokens`
- 长文本展示不便：已在前端提供“紧凑输出”和“展开/收起”切换

## 开发建议
- 新增采集源：在 `crawler.py` 中仿照内置类实现 `fetch_data/clean_results/to_display_schema`
- 新增工具：在 `admin.py` 的 `_ai_tools_defs` 与 `_execute_tool_call` 中添加声明与实现
- 扩展分析：在 DEMO 基础上可增加面向报告的结构化输出（JSON）以便进一步渲染与下载

