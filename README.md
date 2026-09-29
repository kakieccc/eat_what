# 今天吃什么

移动端优先的线下用餐决策 Web 应用。只使用真实高德 POI、真实步行路线、OpenAI-compatible LLM 与 PostgreSQL，不提供模拟运行模式。

## 本机运行

要求：Node.js LTS、pnpm、uv，以及一个可连接的 PostgreSQL 数据库。开发端口为前端 `5173`、后端 `8000`。本项目后端虚拟环境位于 `src/backend/.venv`，Python 3.12；不使用系统 Python 安装依赖。

```bash
cd src/backend
uv sync --frozen
cp .env.example .env
```

填写 `src/backend/.env`：

- `DATABASE_URL`：`postgresql+asyncpg://USER:PASSWORD@localhost:5432/food_nav`。
- `AMAP_WEB_SERVICE_KEY`：高德 Web 服务 Key，需有 POI 搜索、详情、逆地理编码、输入提示和步行路径权限及配额。
- `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`：支持工具调用结构化输出的 OpenAI-compatible 模型。Base URL 通常包含 `/v1`，以实际服务商要求为准。
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

填写 `VITE_AMAP_JS_KEY`、对应 `VITE_AMAP_SECURITY_CODE` 和 `VITE_API_BASE_URL=http://localhost:8000/api/v2`。前端 Key 需要设置允许的域名；它与服务端 Web 服务 Key 不可混用。环境变量修改后重启 Vite。

```bash
pnpm dev --host localhost
```

打开 <http://localhost:5173>。不要混用 `127.0.0.1` 与 `localhost`，否则会影响 CORS。手机通过普通局域网 HTTP 访问的定位不属于本轮验收；浏览器定位需要安全上下文。

## 功能

- 首页设置预算、步行上限、菜系、场景、人数、餐段和自然语言条件。
- 搜索地址、浏览器定位（转换坐标）、点击高德地图选点，主动确认位置。
- LangGraph 显式工作流：搜索、硬过滤、有限路线请求、规则评分、LLM 重排、多样性和证据理由；执行状态由 PostgreSQL Task 管理。
- Fetch-based SSE 业务进度；硬约束变更暂停确认；断流后查询结果恢复。
- 八种 Refine API 动作；常用五种直接展示为快捷按钮。
- 选择餐厅、查看路线、打开高德导航、保存历史和基础偏好。

人均和营业信息未知时保留候选并提示，不声称已满足预算或正在营业。无可行路线淘汰候选；服务请求失败返回错误。无符合条件的候选正常返回空结果，不自动放宽条件。

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

真实集成测试要求独立测试数据库，预先准备与被测版本一致的业务表结构。在本地环境中设置 `TEST_DATABASE_URL`、`TEST_ORIGIN`（含 `latitude`、`longitude`、`address` 的 JSON）、`FOOD_LIVE_TESTS=1` 后执行 `uv run pytest -m live -v`。它会产生真实 API 调用和测试业务记录，不会自动删除数据库。真实前端 E2E 另需 `TEST_ADDRESS`。

设置独立 PostgreSQL 的 `TEST_DATABASE_URL`（`postgresql+asyncpg://`）后，常规 `pytest` 会在临时 schema 中验证创建、调整、确认恢复、幂等冲突、租约失效和失败终态，并清理该 schema。未配置时此测试明确 skipped。

未配置真实测试环境时 live 用例明确 skipped，不代表通过。查看 [验证记录](docs/verification.md) 与 [演示脚本](docs/demo-script.md)。

## 设计与运维边界

- `app/main.py` 创建应用并挂载路由；`app/api` 负责 HTTP Schema、路由、SSE 帧编码和统一错误处理。
- `app/application` 按 decision、places、history 等用例组织命令、查询和接口；`app/workflows/food_decision` 存放 LangGraph State、节点、事件和 Prompt；`app/domain` 按 geo、places、preferences、decision 分组放置业务类型和规则。
- `app/infrastructure` 实现高德、LLM、缓存、PostgreSQL 仓储与 Task Worker。`app/bootstrap.py` 是具体依赖的唯一组装入口。依赖方向为 API → application → workflows/domain，基础设施实现内层接口。
- `app/application/decision/commands.py` 编排创建、调整、确认恢复和幂等；`queries.py` 读取结果，`runner.py` 协调 Task 与 Graph，`streaming.py` 重放事件。跨表写入使用短事务，外部调用期间不持有数据库事务。
- 业务数据使用 PostgreSQL 表；每个执行请求都有 `Task`、`TaskStep` 和 `TaskEvent`，Task 状态是执行事实来源，结果仍从业务表读取。
- 幂等记录按用户和操作隔离；Task 使用短事务、租约和 `FOR UPDATE SKIP LOCKED` 防止跨进程重复执行。
- 推荐总执行预算默认 20 秒，等待用户确认不计时。较慢模型可能需要提高 `DECISION_TIMEOUT_SECONDS`，性能必须以真实调用衡量。
- 搜索最多 30 个 POI，粗筛最多 15 个，前 8 个查路线，并发最多 3。详情只查询最终候选。
- 过期缓存和幂等记录由后续运维任务负责清理；不清除业务历史。
- `GET /api/v2/health/live` 检查进程；`GET /api/v2/health/ready` 检查数据库与工作流初始化，不发起收费上游调用。
- PWA、生产部署、自动长期偏好学习、收藏、账号、骑行驾车和评测看板均不在本轮范围。
- 当前版本包含用户登录和账户归属；不提供跨设备同步以外的长期偏好学习。

## API 资源

- `GET /api/v2/resolved-locations`：按经纬度解析位置。
- `GET /api/v2/location-suggestions`：查询位置建议。
- `GET /api/v2/places`、`GET /api/v2/places/{placeKey}`：查询地点集合或单个地点。
- `POST /api/v2/decision-runs`、`GET /api/v2/decision-runs/{runId}`：创建或读取决策。
- `GET /api/v2/decision-runs/{runId}/events`：订阅决策的 SSE 事件资源。
- `POST /api/v2/decision-runs/{runId}/refinements`：创建一次调整后的子决策。
- `PATCH /api/v2/decision-runs/{runId}`：确认条件或恢复决策执行，返回 `202` 后继续订阅事件。
- `GET /api/v2/discovery-sessions`、`GET /api/v2/discovery-sessions/{sessionId}/decision-runs`：读取历史会话及其决策。
- `POST /api/v2/place-choices`：创建地点选择记录。
- `GET /api/v2/preferences`、`PUT /api/v2/preferences`：读取或完整替换偏好资源。

普通响应统一使用 `{ success, data, meta }`，异常统一使用 `{ success, error, meta }`。创建资源返回 `201` 和 `Location` 响应头。

API 文档由 FastAPI 的 `/docs` 和 `/openapi.json` 提供。集成依据：[高德 POI](https://lbs.amap.com/api/webservice/guide/api-advanced/search)、[步行路线](https://lbs.amap.com/api/webservice/guide/api/direction)、[坐标转换](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom)。
