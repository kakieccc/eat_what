# 今天吃什么

移动端优先的线下用餐决策 Web 应用。使用真实高德 POI、OpenAI-compatible LLM 与 PostgreSQL，按用户确认位置周围的直线半径推荐餐厅，导航直接打开高德，不提供模拟运行模式。

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

先创建数据库和数据库用户，并执行当前 Alembic 迁移准备业务表结构；应用启动时会检查数据库连接并启动持久化 Task Worker：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

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

- 首页设置预算、搜索半径、菜系、场景、人数、餐段和自然语言条件。半径固定为 500 米、1 km、2 km、5 km，默认 2 km，表示以确认位置为中心的直线范围。
- 搜索地址、浏览器定位（转换坐标）、点击高德地图选点，主动确认位置。
- LangGraph 显式工作流：搜索、条件过滤、距离评分、LLM 重排、多样性和证据理由；执行状态由 PostgreSQL Task 管理。
- Fetch-based SSE 业务进度；硬约束变更暂停确认；断流后查询结果恢复。
- 八种 Refine API 动作；常用五种直接展示为快捷按钮。
- 选择餐厅、查看直线距离、在高德查看目标地点、保存历史和基础偏好。

人均和营业信息未知时保留候选并提示，不声称已满足预算或正在营业。实际道路距离可能长于直线距离。服务请求失败返回错误。无符合条件的候选正常返回空结果，不自动放宽条件。

## 验证

```bash
cd src/backend
uv run ruff check app tests
uv run mypy app
uv run pytest -q

cd ../frontend
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm e2e
```

后端 `tests/` 包含规则、SSE、Worker 和模块边界单元测试，以及使用真实 PostgreSQL 的事务、任务执行和 HTTP 集成测试；高德和 LLM 使用测试替身，不发起外部请求。

数据库测试只读取显式设置的 `TEST_DATABASE_URL`，要求数据库名称以 `_test` 结尾，并为每个测试创建独立 schema，结束后只删除该 schema。测试账号需要创建 schema 的权限；不读取应用 `.env` 中的数据库连接。未设置该变量时，数据库测试会跳过，跳过不代表通过。

```bash
cd src/backend
# 指向独立测试数据库；用实际测试账号与端口替换示例值。
TEST_DATABASE_URL='postgresql+asyncpg://test_user:test_password@127.0.0.1:5432/eat_what_test' uv run pytest -q
# 仅运行不需要数据库的用例：
uv run pytest -q -m 'not database'
```

真实上游联调仍需要有效 Key；真实前端 E2E 另需 `TEST_ADDRESS`。

## 设计与运维边界

- `app/main.py` 创建应用并挂载路由；`app/api` 使用扁平结构：`router.py` 汇总路由，`dependencies.py` 提供公共依赖，`schemas.py` 定义公共响应与错误模型，`errors.py` 处理异常及错误响应声明，`health.py` 提供健康检查，`middleware.py` 注册中间件。
- `app/modules` 按 auth、location、places、preferences、history、choice、task、decision 组织业务代码。模块内 `router.py` 处理 HTTP，`schemas.py` 定义 Pydantic 请求、响应与可复用数据结构，`models.py` 定义 ORM 表，`service.py` 编排业务用例，`repository.py` 实现存储，`ports.py` 定义依赖协议。简单模块仅保留需要的文件，location 和 history 不创建自己的 ORM 表。
- 业务路由通过模块的 `dependencies.py` 注入 service；`app/container.py` 保存进程级共享实例，`app/bootstrap.py` 统一组装并通过 lifespan 管理资源。`app/infrastructure` 保留高德、LLM 和共享数据库设施；密码哈希实现位于 `app/modules/auth/passwords.py`；Alembic 在 `migrations/env.py` 中统一加载业务 ORM 模型与高德缓存模型。
- `infrastructure/amap/provider.py` 编排地图操作，`client.py` 管理 HTTP、超时、并发、请求间隔和重试，`schemas.py` 定义高德响应及缓存封装，`mappers.py` 转换坐标和业务数据，`cache.py` 读写缓存，`models.py` 定义缓存表。`location/ports.py` 的 `LocationProvider` 与 `places/ports.py` 的 `GeoPlaceProvider` 由同一适配器实现；菜系推断位于 `places/rules.py`，搜索与详情统一经过 `PlaceService`。
- `app/modules/decision/service/` 内的 `commands.py` 编排创建、调整、确认恢复和幂等，`queries.py` 读取结果，`runner.py` 协调 Task 与 Graph，`streaming.py` 重放事件，模块内的 `sse.py` 编码 SSE 帧；`repository/` 包含存储、事务实现和 mapper；`rules/` 存放筛选、评分和调整规则；`workflow/` 保留 LangGraph State、节点、事件和 Prompt。
- `decision/service/llm.py` 组织偏好解析、候选重排和推荐理由，统一调用 `rules/llm.py` 校验菜系、候选与事实证据；LLM 输出模型定义在模块的 `schemas.py`。`infrastructure/llm/provider.py` 只负责通用结构化调用、模型参数和调用异常转换，通过 `StructuredLlm` 协议注入业务服务。
- `app/modules/task/repository.py` 管理任务持久化，`service.py` 中的 Worker 通过回调执行任务；运行类型位于 `types.py`，租约异常位于 `errors.py`。`location/geometry.py` 提供距离计算，供高德适配器复用。
- service、rules 和 workflow 不直接引用 ORM 或 SQLAlchemy Session。跨模块 ORM 联查保留在持久化实现中，高德适配器保留基础设施缓存读写。choice 的业务判断由 service 承担，检查、选择写入及幂等记录仍在同一事务内完成；跨表写入使用短事务，外部调用期间不持有数据库事务。
- 业务数据使用 PostgreSQL 表；每个执行请求都有 `Task`、`TaskStep` 和 `TaskEvent`，Task 状态是执行事实来源，结果仍从业务表读取。
- 幂等记录按用户和操作隔离；Task 使用短事务、租约和 `FOR UPDATE SKIP LOCKED` 防止跨进程重复执行。
- 推荐总执行预算默认 20 秒，等待用户确认不计时。较慢模型可能需要提高 `DECISION_TIMEOUT_SECONDS`，性能必须以真实调用衡量。
- 搜索最多 30 个 POI，重排前最多保留 10 个候选，最终最多推荐 3 家。距离评分使用直线距离与所选半径；详情只查询最终候选。
- 地点搜索将最多五个关键词去空白、去重后分别查询，每个关键词最多两页、每页 25 条，以 OR 语义合并；按地点 ID 去重，按直线距离及 ID 排序后截断到 `limit`。任一查询失败会取消并等待其他查询，不返回部分结果。`GET /places/{placeKey}` 仍读取用户已保存的推荐地点。
- 高德只在 HTTP 层重试，最多三次，使用指数退避与抖动；网络错误、HTTP `429/500/502/503/504` 和官方瞬时错误码可重试，遵守 `Retry-After` 与剩余预算。Key、权限、参数、每日配额及未知错误不重试，按分钟限制的 `10004` 不在本次调用中重试。各调用使用自身预算与推荐剩余预算中更早的截止时间。
- 仅成功且通过响应校验和业务数据转换的结果会缓存，常规缓存 `AMAP_CACHE_TTL_SECONDS=600`，空结果缓存 `AMAP_EMPTY_CACHE_TTL_SECONDS=30`。缓存键由接口路径和参数生成，响应与 `fetched_at` 分开保存；命中缓存保留原始采集时间。损坏内容视为未命中，数据库读写失败继续报错；外部 HTTP 请求期间不持有数据库事务。
- 前端定位已转换为 GCJ-02，后端直接按高德坐标使用；经纬度格式与导航 URL 由适配器处理。请求日志只记录操作、耗时、次数、缓存命中及错误分类，不记录 Key 或带 Key 的 URL。
- 过期缓存和幂等记录由后续运维任务负责清理；不清除业务历史。
- `GET /health/live` 检查进程；`GET /health/ready` 检查数据库与工作流初始化，不发起收费上游调用。
- PWA、生产部署、自动长期偏好学习、收藏、账号、骑行驾车和评测看板均不在本轮范围。
- 当前版本包含用户登录和账户归属；不提供跨设备同步以外的长期偏好学习。
- 新工作流版本为 `6`、提示词版本为 `3`。部署前停止后端与 Worker，执行到 `0005_radius_only` 迁移，再启动新版本；迁移删除旧时长条件、路线字段与专用缓存表，并将旧未完成任务标记为 `WORKFLOW_UPGRADED`。已完成历史与原始 JSON 快照保留，读取时仅保留当前字段；旧记录使用其他半径时，重新推荐前必须选择四档之一。前端草稿迁移到版本 `2`，保留旧半径并提示重新选择。

## API 资源

- `GET /resolved-locations`：按经纬度解析位置。
- `GET /location-suggestions`：查询位置建议。
- `GET /places`、`GET /places/{placeKey}`：查询地点集合或单个地点。
- `POST /decision-runs`、`GET /decision-runs/{runId}`：创建或读取决策。
- `GET /decision-runs/{runId}/events`：订阅决策的 SSE 事件资源。
- `POST /decision-runs/{runId}/refinements`：创建一次调整后的子决策。
- `PATCH /decision-runs/{runId}`：确认条件或恢复决策执行，返回 `202` 后继续订阅事件。
- `GET /discovery-sessions`、`GET /discovery-sessions/{sessionId}/decision-runs`：读取历史会话及其决策。
- `POST /place-choices`：创建地点选择记录。
- `GET /preferences`、`PUT /preferences`：读取或完整替换偏好资源。

普通响应统一使用 `{ success, data, meta }`，异常统一使用 `{ success, error, meta }`。创建资源返回 `201` 和 `Location` 响应头。

创建推荐、保存偏好和地点集合查询的 `radiusMeters` 只接受 `500 / 1000 / 2000 / 5000`，默认 `2000`，其他值返回 `422`。Refine 动作 `changeRadius` 使用 `{ "action": "changeRadius", "value": 1000 }`，支持扩大或缩小范围；旧半径需先执行该动作再做其他调整。自然语言中有效距离经过现有确认流程，明确指定其他距离返回 `UNSUPPORTED_RADIUS`，不自动取整或根据时间估算距离。历史响应保留原半径，读取类型与新请求校验分开。

API 文档由 FastAPI 的 `/docs` 和 `/openapi.json` 提供。集成依据：[高德 POI](https://lbs.amap.com/api/webservice/guide/api-advanced/search)、[地点标注](https://lbs.amap.com/api/uri-api/guide/mobile-web/point)、[坐标转换](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom)。
