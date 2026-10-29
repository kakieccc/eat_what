# TODO

更新时间：2026-10-28。按当前部署规模重新排序，括号内保留原清单编号。

## 部署基线

- 服务器：2 核 2 GB，PostgreSQL 暂按同机部署估算。
- Nginx 提供 HTTPS、前端静态文件和 API 反向代理；API 使用 `--workers 1`。
- 推荐在 API 进程内执行：`TASK_CONCURRENCY=2`，全局 `queued + running` 最多 4 条，每用户最多 1 条。
- 每用户滚动 60 秒最多受理 3 条新推荐，新建、重试和调整条件共用限额；幂等回放不额外计数。
- 偏好学习每天独立执行一次，临时数据清理每小时执行；两者与业务低峰错开，不作为常驻 Worker。

以下优先级基于这套配置；扩容项单独列出触发条件，当前先处理本机资源保护与实际调用成本。

第 1、3、4 条的代码与回归验证已完成；当前上线前剩余第 2 条：目标机部署和容量验收。

## P1：上线前完成

- [x] **1. 限制实际密码计算并发，避免登录高峰挤占 CPU 和内存（原 8，已完成）**

  已完成：登录、注册、修改密码共用实际计算槽位，默认运行 1 个、最多等待 2 人、最多等待 1 秒；保留 Argon2 参数和不存在账号的校验路径，已有 IP、用户名等认证限流继续生效。

  行为：满载或等待超时返回 `503 AUTH_BUSY`、`Retry-After: 1`；等待请求取消后移出队列，正在计算的请求取消后仍占用槽位，直至线程实际结束。应用关闭时停止受理并等待计算结束。

  回归：[资源保护测试](src/backend/tests/test_resource_limits.py) 覆盖排队上限、超时、两类取消、异常释放、关闭等待及真实 Argon2 校验；认证入口繁忙时不写入凭据、不设置登录 Cookie。目标机内存、CPU 和混合负载验收仍由第 2 条完成。

  位置：[密码计算](src/backend/app/modules/auth/passwords.py)、[认证服务](src/backend/app/modules/auth/service.py)。

- [ ] **2. 落地单机部署并完成目标服务器容量验收（原 3 的剩余验收与连接预算）**

  现状：代码已有并发、准入和取消隔离回归；目标机的进程守护、反向代理、定时调度及 2 GB 内存峰值尚未验收。仓库目前以启动命令和 cron 示例为主。

  本地进展：2026-10-29 已完成独立 API / PostgreSQL 容器的受限压测，合计额度 2 核、1.5 GiB；验证 100 用户突发、双任务冷缓存、8 条 SSE、登录及后台命令叠加，结果见根目录 [压力测试记录](STRESS_TEST.md)。这是预算模拟，未替代目标机整机和真实上游验收，本项保持未完成。

  处理：落实一个 API 进程及自动重启，前端只部署 `dist`，核对同源 HTTPS 和 SSE 流式转发。启用每日偏好学习和每小时清理，错峰执行并收集退出码；验证 PostgreSQL 备份与恢复。

  资源预算：API 的两个推荐槽位共享一个数据库连接池，上限为 10 个连接；偏好批处理、清理命令各自另建连接池，上限也各为 10，均按需建立连接。核对数据库总连接预算并预留管理连接，不能只按 API 进程数估算。

  验收：在目标机覆盖两条推荐同时执行、四条任务受理及后续拒绝，并叠加登录、多标签页查询和定时任务场景；记录总内存峰值、CPU、数据库等待、接口延迟、推荐耗时和排队超时率。先用可控上游验证，再用少量真实地图与 LLM 调用确认配额和时延；依据结果调整并发和队列大小。

  位置：[部署与调度说明](README.md)、[资源配置](src/backend/app/core/config.py)、[连接池](src/backend/app/infrastructure/database/session.py)、[启动与关闭](src/backend/app/bootstrap.py)。

## P2：近期优化

- [x] **3. 合并同键冷缓存请求，减少重复地图调用（原 5，已完成）**

  已完成：现有地图适配器按操作和参数合并在途请求，获得执行权后重新检查缓存。共享通过校验的原始响应，各调用再按自己的位置转换结果；不新增跨进程协调或缓存基础设施。

  行为：共享请求使用独立操作期限，各等待者保留自己的截止时间；首调用方取消或超时不影响其他等待者。最后一个等待者退出时取消共享任务，成功、失败及取消均回收在途记录；错误响应不写入缓存。

  回归：[资源保护测试](src/backend/tests/test_resource_limits.py) 验证十个同键冷请求仅调用一次上游、不同键并发、不同起点距离正确，以及取消、独立期限、失败恢复、坏缓存替换和二次缓存检查。使用模拟上游，未调用真实高德。

  位置：[地图适配器](src/backend/app/infrastructure/amap/provider.py)、[原始响应缓存](src/backend/app/infrastructure/amap/cache.py)。

- [x] **4. 给 SSE 连接设置边界并减少认证查询（原 6，已完成）**

  已完成：当前 API 进程默认每用户最多 2 条 SSE 连接，总数最多 8 条。发送响应头前获取名额，个人超限返回 `429 USER_STREAM_LIMIT_REACHED`，总数超限返回 `503 STREAM_CAPACITY_REACHED`，均附 `Retry-After: 2`。

  行为：整个响应生命周期占用名额，首帧前断开、终态和异常均释放；会话与用户使用单次联查，正常等待轮次从 4 条 SQL 降至 3 条，仍每秒检查撤销状态。前端超限后改用正常查询兜底，不快速重连；轮询频率保持不变，待第 2 条实测后再调整。

  回归：[ASGI 与数据库测试](src/backend/tests/test_stream_limits.py) 覆盖个人和总数限制、首帧前断开、发送失败、权限错误、会话撤销和实际 SQL 数；[浏览器测试](src/frontend/tests/sse-limits.browser.mjs) 验证两种超限均只尝试一次 SSE，随后正常轮询取得完成结果，已受理任务不丢失。

  位置：[SSE 入口](src/backend/app/modules/decision/router.py)、[等待循环](src/backend/app/modules/decision/service/streaming.py)、[认证查询](src/backend/app/modules/auth/repository.py)、[前端订阅与查询兜底](src/frontend/src/components/background-activity.tsx)。
