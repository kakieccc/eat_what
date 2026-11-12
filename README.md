# 今天吃什么

**从附近出发，找到合心意的一餐。**

一个支持自行部署的附近餐厅推荐应用。输入出发位置、预算和本餐需求，结合高德数据与模型匹配，默认给出最多 **3 家**餐厅；对比距离、人均、评分和推荐理由，确认一家，保存这次选择。

[在线地址](https://eat.kakie.site)

[产品功能](#产品功能) · [快速开始](#快速开始) · [开发指南](#开发指南) · [配置说明](#配置说明) · [部署与运维](#部署与运维) · [常见问题](#常见问题)

## 产品功能

| 功能 | 可以做什么 |
| --- | --- |
| 从附近开始 | 使用浏览器定位、搜索地址或地图选点，确定出发位置 |
| 按条件选餐 | 设置人均预算、500 米 / 1 km / 2 km / 5 km 搜索范围、限定食物与排除菜系，补充人数、餐段和本餐需求 |
| 对比推荐 | 查看高德地点信息、直线距离、参考人均、评分和推荐理由|
| 继续调整 | 选择更近、更便宜、评分更高、换个口味、换一批，或修改预算、范围、排除某家餐厅 |
| 跟踪进度 | 查看排队与推荐步骤，切换页面继续跟踪；提交状态不明时可重新确认，失败后可手动重试 |
| 保存个人偏好 | 保存常用条件后同步首页预填；开启偏好学习后会自动学习选餐偏好，支持每日总结，也可关闭使用手动保存 |
| 回看与出发 | 确认餐厅后保存用餐历史，打开高德查看目的地，或按类似条件开始下一餐 |
| 双端界面 | 桌面端提供侧栏、条件概览、列表与地图并排视图、历史表格；移动端保留底部导航与单列操作 |

### 一次选餐流程

1. **注册并登录**，确认出发位置。
2. **填写本餐条件**。提供 12 个常见食物分类，也可以选择“其他”自行输入；更多需求放在“补充说明”或“更多条件”中。
3. 点击 **“帮我选一家”**，等待推荐；不满意时调整条件或换一批。
4. 点击 **“选这家”** 保存决定。确认后本次选餐结束，下一餐从“开始新的选餐”开始。

### 推荐依据与边界

- **位置与预算**：搜索范围和展示距离均为直线距离；已知参考人均超出预算的餐厅会被排除，人均未知的餐厅可能保留并提示。
- **食物条件**：限定食物最多 5 项，满足其中任意一项即可；排除菜系最多 12 项。同一项不能同时限定和排除。
- **本餐需求**：人数、餐段和补充说明用于匹配排序；明确限制请填写在预算、范围和食物条件中。
- **排序与空结果**：默认按规则评分 80%、模型匹配评分 20% 排序。模型排序失败时回退到规则评分；没有合适餐厅时返回空结果，由用户调整条件。
- **数据时效**：营业、价格、座位与接待情况以商家实际信息为准，道路距离以导航为准。食物类型判断不能替代配料、过敏等饮食安全核实。

## 快速开始

### 准备依赖

| 依赖 | 要求 |
| --- | --- |
| Python | **3.12**，使用 [uv](https://docs.astral.sh/uv/) 管理环境与依赖 |
| Node.js | **22.12.0 或更高版本** |
| pnpm | **11.9.0**，与前端 `packageManager` 一致 |
| PostgreSQL | 建议使用 16；提前创建数据库和有建表权限的账号 |
| 高德服务 | Web 服务 Key、JavaScript API Key、对应的安全密钥及所需接口额度 |
| 模型服务 | 支持 Responses API 与下述结构化输出要求的服务和模型 |

浏览器需支持 Web Locks、BroadcastChannel。

以下为首次安装步骤。已有 `.env` 时直接核对和编辑，不要用模板覆盖现有凭据。

### 1. 启动后端

从仓库根目录执行：

```bash
cd src/backend
uv sync --frozen
cp .env.example .env
```

编辑 `src/backend/.env`，字段参考[后端配置模板](src/backend/.env.example)：

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串，例如 `postgresql+asyncpg://USER:PASSWORD@localhost:5432/food_nav` |
| `AMAP_WEB_SERVICE_KEY` | 高德 Web 服务 Key，用于地点搜索、详情、逆地理编码与输入提示 |
| `LLM_API_KEY` | 模型服务 API Key |
| `LLM_BASE_URL` | 模型服务的 API Base URL；模板地址仅为示例，请按所选服务填写 |
| `LLM_MODEL` | 所选服务中的模型 ID |

**模型兼容要求**：当前后端调用 Responses API，并使用 JSON Schema 结构化输出；服务与模型还需接受 `reasoning.effort="none"` 和 `temperature` 参数。仅兼容 Chat Completions 的接口不能直接替换使用，调用实现见 [provider.py](src/backend/app/infrastructure/llm/provider.py)。

确认数据库已创建后，初始化表结构并启动开发服务：

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host localhost --port 8000 --reload --no-access-log
```

推荐 Worker 随 API 进程启动，无需单独启动任务服务。

### 2. 启动前端

另开终端，从仓库根目录执行：

```bash
cd src/frontend
pnpm install --frozen-lockfile
cp .env.example .env
```

编辑 `src/frontend/.env`，字段参考[前端配置模板](src/frontend/.env.example)：

| 变量 | 用途 |
| --- | --- |
| `VITE_API_BASE_URL` | 后端地址，本地为 `http://localhost:8000` |
| `VITE_AMAP_JS_KEY` | 高德 JavaScript API Key，需配置允许访问的域名 |
| `VITE_AMAP_SECURITY_CODE` | 与 JavaScript API Key 对应的安全密钥 |

```bash
pnpm dev
```

打开 **<http://localhost:5173>**，注册账号后开始选餐。前后端的高德 Key 用途不同，需要分别配置。

### 3. 检查服务

| 地址 | 用途 |
| --- | --- |
| [localhost:5173](http://localhost:5173) | 前端入口 |
| [localhost:8000/docs](http://localhost:8000/docs) | 交互式 API 文档 |
| [localhost:8000/openapi.json](http://localhost:8000/openapi.json) | OpenAPI 描述 |
| [localhost:8000/health/live](http://localhost:8000/health/live) | 进程存活检查 |
| [localhost:8000/health/ready](http://localhost:8000/health/ready) | 数据库连接检查 |

健康检查不代表高德和模型服务已验证可用；完成一次选餐才能验证这条调用链路。

## 开发指南

### 项目结构

```text
src/
├── frontend/
│   ├── src/
│   │   ├── pages/          # 首页、推荐、历史、偏好、地点与登录页面
│   │   ├── components/     # 表单、预算、地图、餐厅卡片与导航
│   │   ├── lib/            # API、登录状态、草稿、推荐与 SSE
│   │   ├── styles.css      # 基础与移动端样式
│   │   └── desktop.css     # 桌面端样式
│   └── package.json
└── backend/
    ├── app/
    │   ├── api/            # 路由汇总、中间件、错误响应与健康检查
    │   ├── core/           # 配置、基础模型与通用约束
    │   ├── infrastructure/ # 数据库、高德与模型服务适配
    │   ├── modules/        # 认证、推荐、餐厅、偏好、历史、选择与任务
    │   ├── bootstrap.py    # 服务组装与 Worker 生命周期
    │   └── maintenance.py  # 临时数据清理
    ├── alembic/            # 数据库迁移
    └── pyproject.toml
```

前端使用 React 19、TypeScript、Vite、Tailwind CSS，配合 TanStack Query、Zustand、React Hook Form 和 Zod。后端使用 FastAPI、Pydantic、SQLAlchemy、Alembic 和 LangGraph，数据持久化到 PostgreSQL。

### 推荐链路

```mermaid
flowchart LR
    UI["React 桌面与手机界面"] -->|"HTTP 请求"| API["FastAPI"]
    UI -->|"地图展示"| JS["高德 JavaScript API"]
    API --> DB[("PostgreSQL")]
    API -->|"创建推荐任务"| Worker["Worker + LangGraph"]
    Worker -->|"地点检索与详情"| AMap["高德 Web 服务"]
    Worker -->|"食物判断与匹配排序"| LLM["Responses API 模型服务"]
    Worker --> DB
    API -->|"SSE 进度"| UI
```

单次推荐依次经过 **检索 → 食物筛选 → 匹配排序 → 多样性选择 → 推荐理由**，流程定义在 [graph.py](src/backend/app/modules/decision/workflow/graph.py)。任务状态和进度事件保存在数据库中，由 API 向前端提供查询与 SSE 订阅。

### 从哪里修改

| 改动方向 | 入口 |
| --- | --- |
| 页面、导航与双端布局 | [pages](src/frontend/src/pages)、[app-navigation.tsx](src/frontend/src/components/app-navigation.tsx)、[desktop.css](src/frontend/src/desktop.css)；布局切换点在 [use-desktop.ts](src/frontend/src/lib/use-desktop.ts)，当前为 1024px |
| 表单、默认值与校验 | [preferences-form.tsx](src/frontend/src/components/preferences-form.tsx)、前端 [schemas.ts](src/frontend/src/lib/schemas.ts)、后端 [preferences/schemas.py](src/backend/app/modules/preferences/schemas.py) 与 [decision/schemas.py](src/backend/app/modules/decision/schemas.py) |
| 推荐策略与提示词 | [rules](src/backend/app/modules/decision/rules)、[workflow/nodes](src/backend/app/modules/decision/workflow/nodes)、[workflow/prompts](src/backend/app/modules/decision/workflow/prompts) |
| 外部服务接入 | [infrastructure/amap](src/backend/app/infrastructure/amap)、[infrastructure/llm](src/backend/app/infrastructure/llm) |
| 偏好总结与学习规则 | [modules/preferences](src/backend/app/modules/preferences) |
| 接口与应用组装 | [main.py](src/backend/app/main.py)、[api/router.py](src/backend/app/api/router.py)、各模块的 `router.py`、[bootstrap.py](src/backend/app/bootstrap.py) |

增加或修改请求字段时，同步前端 Zod、后端 Pydantic 和相关调用方。调整页面时，分别检查桌面和手机布局，并确认切换布局不会丢失未提交的输入。

### 常用开发命令

在 `src/frontend` 下执行：

```bash
pnpm typecheck
pnpm lint
pnpm build
```

在 `src/backend` 下执行：

```bash
uv run ruff check app
uv run mypy app
```

按改动范围选择相关检查；`pnpm build` 用于生成生产包。以上静态检查不能替代相关接口与页面交互的验证。

### 数据库变更

在 `src/backend` 下生成并审阅迁移，再应用到开发数据库：

```bash
uv run alembic revision --autogenerate -m "describe_change"
uv run alembic upgrade head
```

当前初始迁移为 `0001`，包含新部署需要的完整表结构。后续结构调整新增迁移，已有数据库升级前先备份并核对当前迁移版本。

### API 联调约定

接口字段与请求示例以运行中的 [API 文档](http://localhost:8000/docs) 为准。前端请求封装见 [api.ts](src/frontend/src/lib/api.ts)。

| 约定 | 说明 |
| --- | --- |
| 登录与注册 | 请求携带 `X-Auth-Intent: web` |
| 登录态 | 使用 Cookie 认证，前端请求携带凭据 |
| 写入操作 | 登录后的写请求需要 `X-CSRF-Token`，令牌由 `/auth/me` 返回 |
| 幂等提交 | 推荐提交、调整、重试与餐厅确认使用 `Idempotency-Key`；同一操作重发复用原 Key，新操作使用新 Key |
| 错误排查 | 查看响应的 `error.code` 和 `X-Request-ID`，对照后端日志定位问题 |
| 限流响应 | 超限返回 HTTP 429；提交频率超限时，`Retry-After` 响应头给出建议等待秒数 |

## 配置说明

连接信息与凭据分别放在前后端 `.env` 中。后端业务参数的默认值统一维护在 [Settings](src/backend/app/core/config.py)，可通过同名环境变量或后端 `.env` 覆盖，例如 `TASK_USER_SUBMISSIONS_PER_MINUTE=5`。

`CORS_ORIGINS` 由 [middleware.py](src/backend/app/api/middleware.py) 直接读取，不在 `Settings` 中声明。

以下为当前默认值：

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `DECISION_RECOMMENDATION_LIMIT` | 3 | 单次推荐返回的餐厅数量上限 |
| `TASK_CONCURRENCY` | 8 | 单个 API 进程同时执行的推荐数 |
| `TASK_MAX_ACTIVE` | 16 | 所有用户合计排队与执行中的任务容量 |
| `TASK_USER_SUBMISSIONS_PER_MINUTE` | 5 | 同一用户滚动 60 秒内受理的推荐提交次数，包含调整与失败重试 |
| `SSE_MAX_CONNECTIONS` | 32 | 单个 API 进程的实时进度连接上限 |
| `SSE_MAX_CONNECTIONS_PER_USER` | 2 | 同一用户在单个 API 进程的实时进度连接上限 |
| `CORS_ORIGINS` | `http://localhost:5173` | 允许访问后端的前端来源，多个地址以逗号分隔 |

另外，同一用户同时最多有 **1 条**排队或执行中的推荐任务。提交频率超过默认限额时，提示“每 60 秒最多提交 5 次推荐，请一分钟后再试”。

后端参数修改后需重载或重启服务。前端 `VITE_*` 变量在启动或构建时读取，修改后需重启开发服务器或重新构建。

## 生产构建与启动

在 `src/frontend` 执行 `pnpm build`，将生成的 `dist/` 交给静态服务器托管。前端路由需要回退到 `index.html`，桌面与手机共用同一份构建产物。

在 `src/backend` 启动生产服务：

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
```

- 使用 HTTPS。优先让前后端同源，或部署在允许 Cookie 认证的同站点域名下；按实际地址设置 `VITE_API_BASE_URL` 与 `CORS_ORIGINS`。
- 反向代理需支持 SSE 持续连接并关闭响应缓冲。
- 当前建议使用一个 API 进程。执行槽位、地图限流与 SSE 连接限制含进程内计数，多进程部署前需重新评估这些限额。
- 更新时保留现有 `.env`，备份数据库并停止旧后端，再安装锁定依赖、执行迁移、重建前端并重启服务。
- 不要提交真实 `.env` 文件或 API Key。

## 常见问题

**定位失败或地图不显示？**

先检查浏览器位置权限、安全上下文，以及高德 JavaScript API Key、安全密钥、允许访问的域名与接口额度。前后端 Key 不能混用；定位失败时仍可搜索地址或手动选点。

**登录后仍被要求登录，或提示跨域错误？**

本地前后端统一使用 `localhost`，不要混用 `localhost` 与 `127.0.0.1`。确认 `CORS_ORIGINS` 包含实际前端地址，浏览器允许相应 Cookie，代理后的访问方式符合部署要求。

**模型调用失败？**

核对 `LLM_BASE_URL`、`LLM_MODEL`、凭据和额度，再检查服务是否支持 Responses API、JSON Schema 及项目传入的参数。仅修改 Base URL 不代表接口兼容。

**为什么提示已有任务、提交过于频繁或服务繁忙？**

同一账号需要先完成当前推荐或确认提交状态；默认滚动 60 秒内最多提交 5 次，调整和重试也占用额度。达到实例任务容量时，新请求会被拒绝，已受理任务继续执行。

**为什么没有合适的推荐？**

当前范围、预算或食物条件可能没有匹配结果。可以手动调整条件后再试，系统不会通过自动放宽这些条件来填满推荐数量。

**开启偏好学习后为什么没有变化？**

确认已经满足用餐记录门槛，并配置每日批处理。开启开关只允许学习，不会自行安装定时任务；已手动保存的字段仍优先使用手动设置。
