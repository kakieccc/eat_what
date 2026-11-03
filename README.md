# 今天吃什么

**从附近出发，找到合心意的一餐。**

今天吃什么是一款面向日常外出就餐的 Web 应用。确认出发位置，填好预算和口味，从附近真实餐厅中获得最多三个推荐；看过距离、参考人均、评分和推荐理由后，选一家，再用高德导航出发。

适配手机和桌面浏览器，支持自行部署。

[功能](#功能) · [开始使用](#开始使用) · [自行部署](#自行部署) · [常见问题](#常见问题)

## 功能

| 功能 | 说明 |
| --- | --- |
| 附近餐厅推荐 | 使用高德地点数据，支持定位、搜索地址和地图选点 |
| 按条件选餐 | 设置人均预算、搜索范围、限定食物和不想吃的菜系；补充人数、餐段及本餐需求 |
| 推荐理由与地图 | 查看餐厅位置、直线距离、参考人均、评分，以及基于已有信息生成的推荐理由 |
| 调整选择 | 选择更近、更便宜、评分更高、换个口味或换一批，也可以修改预算、范围和排除某家餐厅 |
| 后台进度 | 提交后查看排队与推荐进度，切换页面继续跟踪；失败时可手动重试 |
| 个人偏好 | 始终可手动保存常用条件；主动开启偏好学习后，才会每日总结预算、距离和补充偏好，手动设置优先 |
| 用餐历史 | 回看已选餐厅，或按类似条件开始下一次选餐 |
| 高德导航 | 从餐厅详情打开高德查看目的地和导航 |

## 开始使用

1. **注册并登录**：在首页填写本餐条件，也可以先在“偏好”中保存常用设置。
2. **确认出发位置**：使用浏览器定位、搜索地址或在地图上选点。
3. **设置条件**：选择 500 米、1 km、2 km 或 5 km 的搜索范围，填写预算和食物偏好；需要时补充人数、餐段及说明。
4. **获取推荐**：点击“帮我选一家”，等待结果。对结果不满意时，可以调整条件或换一批。
5. **选定并出发**：点击“选这家”保存本次决定，再打开高德导航。确认后本次选餐结束，下一餐可点击“开始新的选餐”。

本餐草稿在当前浏览器会话中保存，进入地图或切换页面时保留。退出登录、登录失效或切换账号时会清空草稿。手动保存的偏好用于下一餐的默认条件，并优先于每日自动总结；本餐草稿保持原样。偏好学习默认关闭，可在“偏好”页开启或关闭，不影响手动修改和保存。

### 推荐信息如何使用

- 搜索范围和展示距离均为**直线距离**，实际道路距离以导航结果为准。
- 限定食物最多填写 5 项，满足其中任意一项即可；不想吃的菜系最多 12 项，可多选，选择“其他菜系”后可自行输入。同一项不能同时限定和排除。
- 已知参考人均超出预算的餐厅会被排除；人均未知的餐厅可能保留，并显示提示。
- 人数、餐段和补充说明用于排序；需要明确限制的条件，请填写在预算、范围和食物条件中。
- 推荐依赖可获得的地点信息，不保证实时营业状态、座位或接待能力。食物类型判断不能替代配料、过敏或其他饮食安全核实。
- 条件下没有合适餐厅时会显示空结果，可以自行调整条件后重试。

## 自行部署

### 环境准备

- Python **3.12** 和 [uv](https://docs.astral.sh/uv/)。
- Node.js **22.12.0 或更高版本**，pnpm **11.9.0**。
- 可连接的 PostgreSQL 数据库；可使用 PostgreSQL 16。
- 高德 **Web 服务 Key**、**JavaScript API Key** 和对应的安全密钥，以及所需接口的调用额度。
- 支持下述接口要求的模型服务账号、API Key 和模型。
- 支持 **Web Locks** 和 **BroadcastChannel** 的现代浏览器。本地使用 `localhost`，公开部署使用 HTTPS。

### 1. 配置并启动后端

首次安装时，在项目根目录执行：

```bash
cd src/backend
uv sync --frozen
cp .env.example .env
```

编辑 `src/backend/.env`：

| 变量 | 配置说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接地址，例如 `postgresql+asyncpg://USER:PASSWORD@localhost:5432/food_nav` |
| `AMAP_WEB_SERVICE_KEY` | 高德 Web 服务 Key，用于地点搜索、详情、逆地理编码和输入提示 |
| `LLM_API_KEY` | 模型服务 API Key |
| `LLM_BASE_URL` | 实际模型服务的 API Base URL，请按所选服务修改模板中的地址 |
| `LLM_MODEL` | 所选服务中的模型 ID |
| `CORS_ORIGINS` | 前端访问地址，默认 `http://localhost:5173`；多个地址用逗号分隔 |

**模型接口要求：**后端调用 Responses API，并使用 JSON Schema 结构化输出；所选服务和模型还需接受 `reasoning.effort="none"` 和 `temperature` 参数。仅支持 Chat Completions 的服务不能直接使用。

先创建数据库和数据库用户，再初始化表结构、启动服务：

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host localhost --port 8000 --workers 1 --no-access-log
```

后端默认运行在 `http://localhost:8000`。推荐任务随 API 启动处理，无需另外启动推荐 Worker。

### 2. 配置并启动前端

在另一个终端，从项目根目录执行：

```bash
cd src/frontend
pnpm install --frozen-lockfile
cp .env.example .env
```

编辑 `src/frontend/.env`：

| 变量 | 配置说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 后端地址，本地使用 `http://localhost:8000` |
| `VITE_AMAP_JS_KEY` | 高德 JavaScript API Key，配置允许访问的域名 |
| `VITE_AMAP_SECURITY_CODE` | 与 JavaScript API Key 对应的安全密钥 |

```bash
pnpm dev
```

打开 **<http://localhost:5173>**，注册账号后即可开始选餐。

前端和后端的高德 Key 用途不同，请分别申请和配置。修改环境变量后需要重启相应服务；本地访问统一使用 `localhost`。

### 3. 启用定时任务

偏好总结和临时数据清理需要由部署环境的调度器运行。以下命令均在 `src/backend` 下执行。

**偏好总结：**建议每天执行一次，仅处理主动开启偏好学习的用户。开启后，确认满 10 餐首次进入学习队列，之后每新增 5 餐触发一次；每批使用最近最多 20 餐记录，总结预算、搜索距离和补充偏好。关闭会取消待学习状态，并阻止正在执行的总结结果写回，已有偏好保持不变。手动固定的偏好优先于自动总结，可通过“恢复自动学习”解除固定。

```bash
uv run python -m app.modules.preferences.batch
```

**临时数据清理：**建议每小时执行一次，清理过期地图缓存、登录会话、幂等记录和认证限流记录，保留用餐历史、偏好样本和任务记录。可先预览数量：

```bash
uv run python -m app.maintenance --dry-run
uv run python -m app.maintenance
```

例如，在系统时区为 `Asia/Shanghai` 的服务器上，可配置以下 cron 条目。请将项目目录、`uv` 路径及日志路径替换为实际值，并检查命令的退出码和日志：

```cron
0 3 * * * cd /path/to/eat_what/src/backend && /absolute/path/to/uv run python -m app.modules.preferences.batch >> /path/to/preferences.log 2>&1
15 * * * * cd /path/to/eat_what/src/backend && /absolute/path/to/uv run python -m app.maintenance >> /path/to/maintenance.log 2>&1
```

### 公开访问与更新

- 在 `src/frontend` 执行 `pnpm build`，将生成的 `src/frontend/dist` 部署到静态服务器；为前端路由配置回退到 `index.html`。
- 使用 HTTPS，配置前端的 `VITE_API_BASE_URL` 和后端的 `CORS_ORIGINS`。前端配置在构建时生效，修改后需要重新构建。
- 反向代理需支持 SSE 持续连接并关闭响应缓冲。保持前后端同源，或部署在允许 Cookie 认证的同站点域名下。
- 小型实例可先使用一个 API 进程。默认同时执行 2 条推荐，所有用户合计最多 4 条排队或执行中的任务；每用户同时最多 1 条，滚动 60 秒内最多受理 3 次新推荐。
- 执行槽位、地图限流和 SSE 连接限制包含进程内计数；当前启动方式使用 `--workers 1`。可通过后端 `.env` 中的 `TASK_CONCURRENCY`、`TASK_MAX_ACTIVE`、`TASK_USER_SUBMISSIONS_PER_MINUTE` 调整推荐限额。
- 初始迁移为 `0001`，新部署在空数据库上执行 `uv run alembic upgrade head`。后续升级前备份数据库并停止旧版后端，执行迁移后再启动。
- API Key 等凭据通过环境配置提供，请勿提交真实 `.env` 文件。

## 常见问题

**定位失败怎么办？**

可以搜索地址或在地图上手动选点。浏览器定位需要位置权限和安全上下文，公开访问时使用 HTTPS。

**为什么提示已有任务或服务繁忙？**

同一账号需要先完成当前推荐或确认提交状态。实例达到任务上限时会拒绝新提交，可以稍后手动重试；已受理任务仍会继续执行。

**可以使用 API 吗？**

可以。启动后访问 [交互式 API 文档](http://localhost:8000/docs) 或 [OpenAPI 描述](http://localhost:8000/openapi.json)。注册、登录请求需要 `X-Auth-Intent: web`；登录后的业务接口使用 Cookie 认证，写入操作还需要 `X-CSRF-Token` 校验。

## 技术栈

- 前端：React、TypeScript、Vite、TanStack Query、Zustand、Tailwind CSS。
- 后端：FastAPI、Pydantic、SQLAlchemy、LangGraph。
- 数据与服务：PostgreSQL、高德地图、支持 Responses API 的模型服务。
