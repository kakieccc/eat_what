# 今天吃什么

移动端优先的线下用餐决策 Web 应用。使用真实高德 POI、OpenAI-compatible LLM 与 PostgreSQL，按用户确认位置周围的直线半径推荐餐厅，导航直接打开高德，不提供模拟运行模式。

当前发布版本：`1.0.0`。

## 本机运行

要求：Node.js LTS、pnpm、uv，以及一个可连接的 PostgreSQL 数据库。开发端口为前端 `5173`、后端 `8000`。本项目后端虚拟环境位于 `src/backend/.venv`，Python 3.12；不使用系统 Python 安装依赖。

```bash
cd src/backend
uv sync --frozen
cp .env.example .env
```

填写 `src/backend/.env`：

- `DATABASE_URL`：`postgresql+asyncpg://USER:PASSWORD@localhost:5432/food_nav`。
- `AMAP_WEB_SERVICE_KEY`：高德 Web 服务 Key，需有 POI 搜索、详情、逆地理编码和输入提示权限及配额。
- 高德连接超时 `AMAP_CONNECT_TIMEOUT_SECONDS=2`，连接池等待超时 `AMAP_POOL_TIMEOUT_SECONDS=1`，读写超时 `AMAP_TIMEOUT_SECONDS=4`；单次业务查询总预算 `AMAP_OPERATION_TIMEOUT_SECONDS=10`，包括缓存、排队、分页和重试。
- 高德全部请求共享 `AMAP_REQUEST_CONCURRENCY=3`；每个接口的请求启动间隔为 `AMAP_REQUEST_INTERVAL_SECONDS=0.5`。限制在单个进程内生效，多进程部署需要统一配额控制。
- `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`：支持 Responses API 和 `text.format=json_schema` 的模型。DeepSeek 的 Base URL 为 `https://api.deepseek.com`，其他服务商以其接口要求为准。
- LLM 调用固定关闭思考模式，通过 SDK 将 Pydantic schema 转为严格的 JSON Schema，并校验返回结果。`LLM_MAX_RETRIES` 默认 `1`，`LLM_TEMPERATURE` 默认 `0`。
- `CORS_ORIGINS=http://localhost:5173`。

不要将密钥提交到版本控制。缺少配置或仍使用 `replace-` 占位符时，后端启动失败。

先创建数据库和数据库用户；在 `src/backend` 执行 Alembic 迁移初始化表，再启动应用及持久化 Task Worker：

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

数据库结构由 `alembic/versions/` 中的迁移文件管理，初始版本为 `0001`。应用启动不再自动建表。修改 ORM 模型后生成迁移，审阅生成的字段、约束和数据处理，再停止后端与 Worker 并升级数据库：

```bash
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
uv run alembic current
```

Alembic 从应用配置读取 `DATABASE_URL`，`alembic.ini` 不保存连接凭据。初始迁移创建当前 14 张业务表和 `alembic_version` 版本表；旧的全表重建命令已移除。

另一个终端启动前端：

```bash
cd src/frontend
pnpm install --frozen-lockfile
cp .env.example .env
```

填写 `VITE_AMAP_JS_KEY`、对应 `VITE_AMAP_SECURITY_CODE` 和 `VITE_API_BASE_URL=http://localhost:8000`。前端 Key 需要设置允许的域名；它与服务端 Web 服务 Key 不可混用。环境变量修改后重启 Vite。

```bash
pnpm dev --host localhost
```

打开 <http://localhost:5173>。不要混用 `127.0.0.1` 与 `localhost`，否则会影响 CORS。手机通过普通局域网 HTTP 访问的定位不属于本轮验收；浏览器定位需要安全上下文。

## 功能

- 首页设置预算、搜索半径、限定食物类型、排除食物、人数、餐段和补充说明。场景标签直接写入补充说明。半径仅支持 500 米、1 km、2 km、5 km 四档，默认 2 km，表示以确认位置为中心的直线范围。
- 首页表单状态实时保存在当前账号的浏览器会话草稿中，进入选址页、返回或确认新位置后保留输入。草稿允许尚未完成的值，提交推荐时再执行完整校验；本次草稿不自动覆盖账户已保存的偏好。
- 长期偏好从多餐记录中总结，用于新选餐预填；手动固定可逐字段恢复自动学习，账户保存不覆盖本餐草稿。满 10 餐首次学习，之后每 5 餐使用最近 20 餐更新。
- 搜索地址、浏览器定位（转换坐标）、点击高德地图选点，主动确认位置。
- 表单合法后直接创建任务。LangGraph 执行表单食物类型检索、详情与硬筛（失败补位）、软评分、多样性和事实理由；执行状态由 PostgreSQL Task 管理。补充说明仅影响排序，即使包含“必须”“只能”也不会修改硬条件。
- 推荐由后台 Worker 执行，应用级任务面板显示排队、节点进度、完成和失败，切换页面继续跟踪。SSE 正常收取事件时暂停轮询，断流或 35 秒没有消息后恢复每 2 秒查询结果；待确认的提交随会话保存，每次等待确认最多 15 秒（含响应正文）；超时提示重新确认，刷新或重试复用同一幂等键，不取消已受理任务。推荐和“选这家”保存完成均不自动跳转，由用户点击查看结果。
- 八种 Refine API 动作；常用五种直接展示为快捷按钮。
- 每次选餐会话确认一个最终餐厅，确认后本次选餐结束，不能改选或继续调整。已选详情只读并保留历史；“开始新的选餐”创建独立会话。支持查看直线距离、在高德查看目标地点和保存基础偏好。

人均信息未知时保留候选并提示，不声称已满足预算。应用不记录或检查营业状态。实际道路距离可能长于直线距离。服务请求失败返回错误。无符合条件的候选正常返回空结果，不自动放宽条件。

## 静态检查

```bash
cd src/backend
uv run ruff check app alembic
uv run mypy app

cd ../frontend
pnpm typecheck
pnpm lint
pnpm build
```

当前保留 Ruff、mypy、TypeScript 和 ESLint 静态检查工具。

## 设计与运维边界

- `app/main.py` 创建应用并挂载路由；`app/api` 使用扁平结构：`router.py` 汇总路由，`dependencies.py` 提供公共依赖，`schemas.py` 定义公共响应与错误模型，`errors.py` 处理异常及错误响应声明，`health.py` 提供健康检查，`middleware.py` 注册中间件。
- `app/modules` 按 auth、location、places、preferences、history、choice、task、decision 组织业务代码。模块内 `router.py` 处理 HTTP，`schemas.py` 定义 Pydantic 请求、响应与可复用数据结构，`models.py` 定义 ORM 表，`service.py` 编排有业务逻辑的用例，`repository.py` 实现存储，`ports.py` 定义依赖协议。简单模块仅保留需要的文件：location 路由直接调用 provider，preferences 路由直接调用 repository；location 和 history 不创建自己的 ORM 表。
- 业务路由通过公共 `ContainerDependency` 访问共享实例，`auth/dependencies.py` 保留登录与 CSRF 校验；`app/container.py` 保存进程级共享实例，`app/bootstrap.py` 统一组装并通过 lifespan 管理资源。`app/infrastructure` 保留高德、LLM 和共享数据库设施；密码哈希实现位于 `app/modules/auth/passwords.py`；`app/infrastructure/database/metadata.py` 统一注册 ORM 模型，供 Alembic 自动生成迁移使用；`alembic/versions/` 保存表结构变更。
- `infrastructure/amap/provider.py` 编排地图操作，`client.py` 管理 HTTP、超时、并发、请求间隔和重试，`schemas.py` 定义高德响应及缓存封装，`mappers.py` 转换坐标和业务数据，`cache.py` 读写缓存，`models.py` 定义缓存表。`location/ports.py` 的 `LocationProvider` 与 `places/ports.py` 的 `GeoPlaceProvider` 由同一适配器实现；保留高德分类与标签，搜索与详情统一经过 `PlaceService`，不从店名硬编码推断菜系。
- `app/modules/decision/service/` 内的 `commands.py` 编排创建、调整和幂等，`queries.py` 读取结果，`runner.py` 协调 Task 与 Graph，`streaming.py` 重放事件，模块内的 `sse.py` 编码 SSE 帧；`repository/` 包含存储、事务实现和 mapper；`rules/` 存放筛选、评分和调整规则；`workflow/` 保留 LangGraph State、节点、事件和 Prompt。
- `decision/service/llm.py` 组织食物硬判断，以及说明、人数和餐段的软评分，统一调用 `rules/llm.py` 校验候选覆盖与事实证据；`rules/explanations.py` 本地组合推荐理由，不再调用模型。LLM 输出模型定义在模块的 `schemas.py`。`infrastructure/llm/provider.py` 只负责通用结构化调用、模型参数和调用异常转换，通过 `StructuredLlm` 协议注入业务服务。
- `app/modules/task/repository.py` 管理任务持久化，`service.py` 中的 Worker 通过回调执行任务；运行类型位于 `types.py`，租约异常位于 `errors.py`。`location/geometry.py` 提供距离计算，供高德适配器复用。
- service、rules 和 workflow 不直接引用 ORM 或 SQLAlchemy Session。跨模块 ORM 联查保留在持久化实现中，高德适配器保留基础设施缓存读写。choice 的业务判断由 service 承担，检查、选择写入及幂等记录仍在同一事务内完成；跨表写入使用短事务，外部调用期间不持有数据库事务。
- 业务数据使用 PostgreSQL 表；每个执行请求都有 `Task`、`TaskStep` 和 `TaskEvent`，Task 状态是执行事实来源。Worker 不再把完整推荐结果重复写入事件表；SSE 在完成后读取业务表生成 `result`，同时兼容旧结果事件。候选表仅保留身份、Run 关联、地点键、排名和 `place_snapshot`，展示与偏好学习共用快照，导航 URL 在读取时生成。
- 幂等记录按用户和操作隔离；Task 使用短事务、租约和 `FOR UPDATE SKIP LOCKED` 防止跨进程重复执行。
- 推荐总执行预算默认 20 秒，从首次领取任务开始计算；检查点保存累计耗时，租约恢复沿用首次启动的截止时间，停机和恢复等待也计入预算。提交阶段不调用模型，预算用于后台检索、硬判断、评分与理由。多轮硬筛补位或较慢模型可能需要提高 `DECISION_TIMEOUT_SECONDS`，性能必须以真实调用衡量。
- 推荐排队默认最多等待 `TASK_QUEUE_TIMEOUT_SECONDS=60` 秒，可配置为 1–3600 秒。独立检查约每秒清理到期任务，不受正在执行的任务阻塞；超时标记为 `QUEUE_TIMEOUT`，通过 SSE 和结果查询提示重新推荐，重试创建新任务。正在执行和租约恢复的任务使用执行预算，不套用首次排队时限；单个 Worker 仍串行执行。
- SSE 建立后立即发送心跳，此后每 15 秒发送一次。等待循环每秒检查会话、用户所属当前 Run、最新 Task 和新增事件，终态才读取完整推荐；PostgreSQL 测试确认正常等待循环为 4 条 SQL，包含会话与用户查询。会话撤销时结束流并清空前端身份，结果事件发送前重读权威结果。
- 时间配置在启动时校验：`LLM_TIMEOUT_SECONDS` 为有限正数且不超过 300 秒，`DECISION_TIMEOUT_SECONDS` 为有限正数且不超过 600 秒，`TASK_LEASE_SECONDS` 为 3–3600 秒，`TASK_POLL_SECONDS` 为 0.1–60 秒。租约至少 3 秒，保证推荐和偏好 Worker 的现有心跳周期短于租约；默认值保持 10、20、60、1 秒。
- 推荐按最多五个关键词轮询分页，每页 25 条，每次 Run 最多八次搜索请求。先去重并排除已知不满足条件的地点，再按评分补全详情；详情失败或补全后不符合条件的餐厅会被剔除，并由其他候选补位。已有候选不足时继续原检索进度，必要时补充同范围通用餐饮搜索；失败候选不会重复进入补位，累计搜索次数和整体超时预算不重置。详情只用较新且非空的字段覆盖，最多保留十个有效候选交给 LLM 匹配与排序，多样性选择最多三家。找不到足够替补时返回较少或空结果并提示，不自动放宽预算或半径。
- `GET /places` 是单页地点查询；推荐流程的跨关键词分页与请求预算由 decision 编排。`GET /places/{placeKey}` 读取用户已保存的推荐地点。未知人均保留并警告；硬食物判断未知或不符合条件的候选剔除。
- 高德只在 HTTP 层重试，最多请求三次，等待时间仅使用本地指数退避 `0.2 × 2^(attempt−1)` 秒，加 0–0.1 秒随机抖动，并受剩余时间预算约束。网络错误、HTTP `429/500/502/503/504` 和官方瞬时错误码可重试。Key、权限、参数、每日配额及未知错误不重试，按分钟限制的 `10004` 不在本次调用中重试。各调用使用自身预算与推荐剩余预算中更早的截止时间。
- 仅成功且通过响应校验和业务数据转换的结果会缓存，常规缓存 `AMAP_CACHE_TTL_SECONDS=600`，空结果缓存 `AMAP_EMPTY_CACHE_TTL_SECONDS=30`。缓存键由接口路径和参数生成，响应与 `fetched_at` 分开保存；命中缓存保留原始采集时间。同键写入冲突时锁定记录，仅允许采集时间不旧于现有记录的响应更新数据和有效期。损坏内容视为未命中，并允许正常响应替换；数据库读写失败继续报错，外部 HTTP 请求期间不持有数据库事务。
- 搜索和详情逐条校验、转换地点；坏记录只跳过该条并记录数量，保留同页正常餐厅。整体响应格式错误仍返回地图响应错误，全页无有效地点按空结果处理。
- 前端定位已转换为 GCJ-02，后端直接按高德坐标使用；经纬度格式与导航 URL 由适配器处理。请求日志只记录操作、耗时、次数、缓存命中及错误分类，不记录 Key 或带 Key 的 URL。
- 过期缓存和幂等记录由后续运维任务负责清理；不清除业务历史。
- `GET /health/live` 检查进程；`GET /health/ready` 检查数据库与工作流初始化，不发起收费上游调用。
- PWA、生产部署、收藏、骑行驾车和评测看板均不在本轮范围。
- 长期偏好使用独立学习 Worker，不进入推荐 Graph；满 10 餐首次总结，之后每 5 餐使用最近 20 餐更新预算、距离和软偏好。
- 当前工作流版本为 `11`、提示词版本为 `10`。检索队列和已检索地点 ID 随任务状态保存；旧工作流版本的待执行任务需要重新生成推荐。表结构变更通过 Alembic 迁移。前端草稿版本为 `8`，旧结构草稿重置一次；同账号刷新保留本次条件、位置和推荐入口，退出、登录失效或切换账号时清空。

## API 资源

- `GET /resolved-locations`：按经纬度解析位置。
- `GET /location-suggestions`：查询位置建议。
- `GET /places`、`GET /places/{placeKey}`：查询地点集合或单个地点。
- `POST /decision-runs`、`GET /decision-runs/{runId}`：创建或读取决策。
- `GET /decision-runs/{runId}/events`：订阅决策的 SSE 事件资源。
- `POST /decision-runs/{runId}/refinements`：为尚未选定餐厅的当前批次创建一次调整后的子决策。
- `GET /discovery-sessions`、`GET /discovery-sessions/{sessionId}/decision-runs`：读取历史会话及其决策。
- `POST /place-choices`：确认最终餐厅，返回 `200`；只提交 `candidateId`。重复确认同一家返回原选择，不能改选。
- `GET /preferences`、`PUT /preferences`：读取有效默认值、来源、手动固定和学习状态；携带 `revision` 完整替换手动固定集合。

普通响应统一使用 `{ success, data, meta }`，异常统一使用 `{ success, error, meta }`。创建资源返回 `201` 和 `Location` 响应头。

选定餐厅后，调整、换批、重试和改选返回 `409 SELECTION_COMPLETED`，不会删除原选择或候选。后端在会话行锁内复查结束状态，避免并发请求绕过规则；已有选择记录直接视为已结束，无需数据库结构迁移。

`DecisionRequest` 由 `origin`、`preferences`、顶层 `requestText`、`mealPeriod`、`partySize` 组成。`Preferences` 只包含预算、半径、`allowedFoods` 和 `excludedFoods`。新建推荐和账户偏好中的限定食物最多 5 项，每项都有搜索机会；超量拒绝，不静默截断。旧历史仍可读取，超过 5 项时需调整条件后重新推荐。食物为自由文本，限定列表内部为 OR，排除列表必须全部明确不匹配；证据不足则剔除并补位。食物类型不能证明配料或过敏安全。

`radiusMeters` 仅接受 `500 / 1000 / 2000 / 5000`。已知价格越界剔除，价格未知保留并提示。说明、人数和餐段仅作软评分，不生成检索条件或改写表单；说明为空时仍评估人数和餐段。模型只能依据明确的分类、标签、距离、人均、评分和营业时间等事实，未知要求不加分但不会淘汰候选；不推断座位、接待能力或当前营业状态。综合分为基础分 30% + 软匹配分 70%。“换个口味”作为附加软排序目标；“更近”“更便宜”“评分更高”保留基础权重调整。模型返回漏候选、重复 ID、越界分数或无效事实证据会使任务失败。

推荐理由按固定规则组合已有事实，保留已校验的软匹配依据、未知人均与评分提示及原有 warnings，不另发模型请求。

账户偏好提供生效默认值和稀疏手动固定集合，默认 `requestText` 最多 1000 字。创建决策必须携带 `prefillSnapshot` 记录初始值和来源；该元数据不进入推荐工作流。Run 的 `request` 保存当前条件，`originalRequest` 保存首次提交条件。偏好保存版本不符返回 `409 PREFERENCE_CONFLICT`。浏览器草稿升级到版本 8，旧草稿重置一次。

### 上线数据库基线

发布版本 `1.0.0` 将开发期的 `0001`–`0006` 合并为单一初始迁移 `0001`，直接创建当前 14 张业务表、索引和约束。该迁移用于全新数据库；旧开发库不能直接套用新迁移链，也不能在未核对结构时仅修改版本表。

全新数据库执行：

```bash
cd src/backend
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

本机 `food_nav` 已删除并从空库执行新基线 `0001` 重建，14 张业务表全部为空，结构与当前 ORM 一致。已有业务数据的其他数据库须先停止 API/Worker、备份并单独核对结构，再制定切换步骤。工作流版本 `11`、Prompt 版本 `10` 保留各自的兼容性含义；前端草稿版本升至 `8`，首次加载清除旧草稿。

API 文档由 FastAPI 的 `/docs` 和 `/openapi.json` 提供。集成依据：[高德 POI](https://lbs.amap.com/api/webservice/guide/api-advanced/search)、[地点标注](https://lbs.amap.com/api/uri-api/guide/mobile-web/point)、[坐标转换](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom)。
