# Family Butler · 家庭管家（Faamily）

> 面向中国家庭的**协作与资料归档**小程序：一个家庭 = 一个数据空间，任务、公告、证件、照护记录都在里面沉淀。

微信小程序 + FastAPI + PostgreSQL 的全栈工程，覆盖 **账号身份 → 家庭组织 → 任务流转 → 文档/保险箱 → 场景模板** 的完整闭环。

| | |
|---|---|
| 后端 | FastAPI 0.115 · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 / SQLite |
| 前端 | 原生微信小程序（10 个页面，4 个 tab） |
| 规模 | 63 个 `/v1` 端点 · 18 张表 · 后端 ~7.6k 行 / 小程序 ~4.1k 行 |
| 质量 | ruff · pytest（18 用例）· detect-secrets 密钥扫描 · GitHub Actions CI |
| 版本 | API `0.7.0` · 迁移 head `0002_email_otp_schema_fix` |

---

## 1. 这个产品解决什么

家庭里的信息是散的：孩子的作业在微信聊天里，老人用药记录在备忘录里，房产证扫描件在个人手机相册里，家电保修单在抽屉里。**换个人就找不到了，出了事没人知道"这事办没办"。**

Faamily 的做法是：以「家庭」为数据边界，把这四类信息收进同一个受控空间：

| 模块 | 解决什么 | 关键设计 |
|---|---|---|
| **账号与身份** | 一个人多个登录方式 | `users` + `user_identities` 分离，同一用户可绑微信/邮箱/手机；游客、邮箱、微信三种登录 |
| **家庭与成员** | 谁属于这个家，谁能干什么 | 邀请码 + 三种角色（owner/admin/member）+ 成员级权限开关 |
| **任务** | 事情派给谁、做完没有 | 完整状态机 + 提交/验收闭环 + 重复任务 |
| **公告与文档库** | 通知与留存 | 共享资料库 + **私密保险箱**（邮箱 OTP 二次验证，邮件发送待接入） |
| **预设场景** | 不想从零配置 | 儿童学习 / 老人照护 / 婴儿照看 / 大件归档 / 宠物照料 一键启用 |
| **VIP 与配额** | 成本可控 | 家庭维度容量配额 + 四档订阅 |
| **审计与后台** | 关键操作可追溯 | 成员变更、保险箱访问、文件删除全部落 `audit_logs` |

### 设计原则

1. **数据隔离是第一优先级** —— 所有业务表强制带 `family_id`，跨家庭访问一律 404 而非 403（不泄露存在性）。
2. **敏感数据走独立通道** —— 保险箱文件需要额外携带短时 `vault_session`，不是靠角色判断。
3. **不自己存文件字节** —— 后端只存元数据与 `storage_key`，文件走对象存储签名直传（已预留，尚未接入）。
4. **场景配置驱动** —— 新增家庭场景不写代码，写模板定义。

---

## 2. 技术栈

```
FastAPI 0.115        SQLAlchemy 2.0.51     Alembic 1.13.3
Pydantic v2          python-jose (HS256 JWT)   slowapi (限流)
PostgreSQL 16        SQLite (本地零依赖开发)    原生微信小程序
```

**双数据库兼容层**（`app/core/types.py`）是本工程的一个特色设计：`GUID` TypeDecorator 在 PG 下走原生 `UUID`，在 SQLite 下退回 `CHAR(36)`；`JSONB` 在 SQLite 下编译为 `JSON`。开发者不需要装 Docker/PostgreSQL 就能跑起全功能环境。

---

## 3. 快速开始

### 3.1 Windows 一键启动（推荐给非后端同学）

```bash
双击 setup.bat
```

脚本会自动：检查 Python → 生成 `.env`（含随机 `JWT_SECRET`）→ 建虚拟环境 → 装依赖 → 建表 → 启动服务。

> ⚠️ `setup.bat` 建的是 `venv/` 目录（历史遗留），而手动流程用的是 `.venv/`。两者都能用，但别混着敲命令。
### 3.2 手动启动（SQLite，零外部依赖）

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # 运行时依赖
pip install -r requirements-dev.txt   # 开发依赖（额外含 pytest / ruff / detect-secrets）

cp .env.example .env             # 或直接跑 setup.bat 生成
# .env 里 DATABASE_URL=sqlite:///./data.db

python init_db.py                # 建表（本地开发用）
# 或者用迁移：alembic upgrade head

uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health          # {"status":"ok","env":"local"}
open http://127.0.0.1:8000/docs             # Swagger UI
```

### 3.3 PostgreSQL（集成 / 生产形态）

```bash
docker compose up -d db                    # 起 postgres:16-alpine

# psycopg 已包含在 requirements.txt 中
# .env: DATABASE_URL=postgresql+psycopg://family_butler:family_butler@localhost:5432/family_butler

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`db/schema.sql` 是 PostgreSQL 的裸 DDL 版本，早于 Alembic 迁移（缺 `vip_subscriptions` 表和 `users` 的两列，见第 10 节第 5 条），可用于一次性导入，但**以 Alembic 迁移为准**。

### 3.4 微信小程序端

1. 用微信开发者工具打开**工程根目录**（`project.config.json` 在根，`miniprogram/` 是小程序根）
2. 改 `miniprogram/utils/config.js` 的 `BASE_URL` 指向你的后端地址
   - 开发者工具里要勾选「不校验合法域名」，或把后端加入小程序后台的 request 合法域名
3. 本地调试用 `http://localhost:8000/v1`；真机必须用 HTTPS 正式域名

---

## 4. 配置项（`.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `local` | 环境标识，回显在 `/health` |
| `DATABASE_URL` | `sqlite:///./data.db` | SQLite 或 `postgresql+psycopg://...` |
| `JWT_SECRET` | 必填 | HS256 签名密钥，**生产必须换** |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `30` | access token 有效期 |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | `30` | refresh token 有效期 |
| `ADMIN_USER_IDS` | 空 | 逗号分隔的 user UUID，拥有后台访问权 |
| `ONLINE_TIMEOUT_MINUTES` | `15` | 后台"在线用户"判定阈值 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | `wx20b921f556e521a3` / 无 | 小程序 `jscode2session` 换取 openid/unionid。**Secret 只写在本地 `.env`** |
| `SMTP_*` | 空 | 邮箱验证码发送（`/auth/email/send-otp` 依赖它；**保险箱 OTP 尚未接入**） |

> 密钥管理约定与轮换流程见第 11 节「安全开发指南」。

---

## 5. API 一览

全部前缀 `/v1`，统一 Bearer Token 认证，响应为 JSON。完整交互式文档见 `/docs`。

### 5.1 认证 `/auth`

| 方法 | 路径 | 说明 | 限流 |
|---|---|---|---|
| POST | `/auth/guest` | 游客登录（匿名用户 + token） | 5/min |
| POST | `/auth/email/register` | 邮箱注册 | 3/min |
| POST | `/auth/email/login` | 邮箱登录 | 10/min |
| POST | `/auth/email/send-otp` | 发送邮箱验证码 | 3/min |
| POST | `/auth/email/verify` | 校验邮箱验证码 | — |
| POST | `/auth/wechat/login` | 微信小程序登录（code → openid/unionid） | 10/min |
| POST | `/auth/refresh` | 刷新 access token | — |
| GET | `/auth/me` | 当前用户 + 已绑定身份 | — |

### 5.2 家庭与成员 `/families`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | `/families` | 创建 / 列出我的家庭 |
| GET/PUT/DELETE | `/families/{family_id}` | 详情 / 更新 / 解散 |
| POST | `/families/join` | 用邀请码加入 |
| GET/POST | `/families/{id}/members` | 成员列表 / 添加成员 |
| PUT | `/families/{id}/members/{user_id}/role` | 改角色 |
| PUT | `/families/{id}/members/{user_id}/permissions` | 改权限开关 |
| DELETE | `/families/{id}/members/{user_id}` | 移除成员 |
| GET/POST | `/families/{id}/invites` | 邀请码列表 / 生成 |
| DELETE | `/families/{id}/invites/{invite_id}` | 作废邀请码 |

### 5.3 任务 `/families/{id}/tasks`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | `.../tasks` | 创建 / 按 assignee、status、due 过滤查询 |
| GET/PUT/DELETE | `.../tasks/{task_id}` | 详情 / 更新 / 软删除 |
| PUT | `.../tasks/{task_id}/status` | 状态流转（服务端校验合法性） |
| POST | `.../tasks/{task_id}/submit` | 提交完成材料（文字说明；附件字段已定义但未接入） |
| GET | `.../tasks/{task_id}/submissions` | 提交历史 |
| PUT | `.../tasks/{task_id}/submissions/{sid}/review` | 通过 / 驳回（驳回必填原因） |

**状态机**（`app/services/task_service.py`）：

```
pending ──→ in_progress ──→ submitted ──→ done
   ↑            │                │
   │            ↓                ↓
   └────────── rejected ←────────┘
```

`done` 是终态；`rejected` 回到 `in_progress` 重新提交。

### 5.4 公告 `/families/{id}/announcements`

`POST` 创建（`attachment_ids` 最多 5 个，但关联逻辑尚未实现）· `GET` 列表 · `GET/PUT/DELETE` 单条（支持置顶、软删除）

### 5.5 文档库与保险箱 `/families/{id}/documents`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | `.../documents/folders` | 创建 / 查询文件夹（`zone=shared\|vault`，支持层级） |
| PUT/DELETE | `.../documents/folders/{folder_id}` | 重命名 / 删除 |
| POST/GET | `.../documents/files` | 登记文件元数据（≤ 20MB）/ 查询 |
| DELETE | `.../documents/files/{file_id}` | 删除（软删 + 释放配额） |
| POST | `.../documents/vault/otp` | 申请保险箱验证码（**邮件发送待接入，当前调试期明文返回**） |
| POST | `.../documents/vault/verify` | 校验 OTP → 换取短时 `vault_session` |
| GET | `.../documents/vault/status` | 查询保险箱会话状态 |

### 5.6 场景 `/scenarios` · `/families/{id}/scenarios`

`GET /scenarios/templates`（含内置模板）· `GET /scenarios/templates/{id}` · `POST /scenarios/templates/seed`（落库）· `GET/POST /families/{id}/scenarios`（查询 / 启用）· `DELETE /families/{id}/scenarios/{instance_id}`（停用）

### 5.7 VIP `/vip`

`GET /vip/catalog`（四档套餐）· `GET /vip/status`（当前订阅）· `POST /vip/subscribe` · `POST /vip/cancel`

### 5.8 后台 `/admin`（需 `ADMIN_USER_IDS` 白名单）

`/admin/dashboard`（总览）· `/admin/users`（注册统计）· `/admin/online`（在线用户）· `/admin/vip`（订阅分布）· `/admin/regions`（地域分布）· `/admin/families`（家庭统计）· `/admin/audit`（审计汇总）

---

## 6. 数据模型

```
users ──┬── user_identities   (wechat / phone / email 多身份绑定)
        ├── memberships ── families ── invites
        ├── task_submissions        （经 tasks）
        ├── files ── folders        (zone: shared | vault | attachment)
        ├── vip_subscriptions
        └── audit_logs
```

18 张表：`users`、`user_identities`、`families`、`memberships`、`invites`、`tasks`、`task_submissions`、`announcements`、`folders`、`files`、`quotas`、`email_verification_otps`、`vault_email_otps`、`vault_sessions`、`scenario_templates`、`scenario_instances`、`audit_logs`、`vip_subscriptions`

统一约定：UUID 主键、`created_at` / `updated_at` 带时区、软删除字段 `deleted_at`、关键表建复合索引（`family_id + 维度`）。

### 权限模型

角色（`memberships.role`）：

| 角色 | 权限 |
|---|---|
| `owner` | 解散家庭、转让户主、管理所有成员、管理邀请码、查看审计 |
| `admin` | 管理任务/公告/文档、增删普通成员（**不能**动 owner 和 admin） |
| `member` | 完成任务、发布公告、访问共享资料 |
| `child` | 已并入 `member`（数据库约束只允许 `owner`/`admin`/`member`），受限能力通过 `permissions` 权限位（如 `restricted`）表达 |

权限判定在 `app/core/permissions.py`，通过 FastAPI 依赖注入实现（`require_owner` / `require_admin` / `require_any_role`），不手写 if 判断。

### 预设场景模板

| key | 名称 | 典型任务类型 | 默认目录 |
|---|---|---|---|
| `child_learning` | 儿童学习 | 作业 / 阅读 / 练琴 / 运动 | 学习资料、作品展示（vault: 成绩单） |
| `elder_care` | 老人照护 | 用药提醒 / 复诊 / 体检 | 健康记录、复诊安排（vault: 证件、保险单） |
| `baby_care` | 婴儿照看 | 喂养 / 睡眠 / 体温 / 疫苗 | 日常记录、疫苗记录（vault: 出生证明、体检报告） |
| `appliance_archive` | 大件归档 | 保修到期 / 年检 / 保养 | 家电、家具（vault: 发票、合同凭证） |
| `pet_care` | 宠物照料 | 喂养 / 驱虫 / 疫苗 / 洗澡 | 日常记录、宠物照片（vault: 宠物证件、医疗报告） |

启用场景时会**幂等地**创建默认文件夹结构（`scenario_service.ensure_scenario_default_folders`）。

---

## 7. 目录结构

```
app/
├── main.py              FastAPI 入口，路由注册，slowapi 限流器
├── db.py                engine / session / get_db 依赖
├── models/__init__.py   18 张表的 SQLAlchemy 2.0 ORM 定义
├── api/                 8 个路由模块（薄层：参数校验 + 调 service）
├── services/            9 个业务服务层（事务、状态机、配额、审计）
├── schemas/             Pydantic 请求/响应模型
└── core/
    ├── config.py        .env 配置
    ├── security.py      JWT 签发与校验
    ├── deps.py          get_current_user / require_admin_user
    ├── permissions.py   角色与权限判定
    └── types.py         跨数据库类型兼容层（GUID / JSONB）
migrations/versions/     Alembic 迁移（0001_init → 0002_email_otp_schema_fix）
miniprogram/             微信小程序（10 页面 + utils/api.js 请求封装）
tests/                   pytest（api/ + services/ 两层）
db/schema.sql            PostgreSQL 裸 DDL
docs/superpowers/        历史设计文档与实施计划
app-overview.md          产品总体设计（角色、范围、非目标）
next-tasks.md            任务清单与进度

# 工具链
pyproject.toml           项目配置（ruff 规则 + pytest 配置）
requirements.txt         运行时依赖
requirements-dev.txt     开发依赖（pytest / ruff / detect-secrets）
.githooks/pre-commit     本地密钥扫描钩子（core.hooksPath 指向此处）
.secrets.baseline        已审查的密钥误报指纹库
.github/workflows/ci.yml CI（secret-scan / lint / test / app-smoke）
```

**分层约定**：`api` 只做参数校验和异常映射，业务逻辑一律下沉到 `services`，ORM 只在 `models` 里定义。跨层依赖单向：`api → services → models`。

---

## 8. 小程序端

10 个页面：`login`、`home`、`tasks`、`task-detail`、`task-create`、`family`、`members`、`profile`、`family-create`、`join-family`；tabBar 为 首页 / 任务 / 家庭 / 我的。

`miniprogram/utils/api.js` 是统一请求层，要点：

- 自动注入 `Authorization: Bearer <access_token>`
- **401 自动刷新** refresh token 并重放原请求
- **并发刷新锁**（`isRefreshing` + `pendingRequests` 队列）——多个请求同时 401 只触发一次刷新，其余排队等待
- 业务错误统一成 `{ code, message, data }` 结构 reject

---

## 9. 测试与代码质量

```bash
pip install -r requirements-dev.txt   # pytest / ruff / detect-secrets

pytest tests -q                       # 18 个用例
ruff check app/ tests/ migrations/    # 代码规范
```

当前 18 个用例，覆盖：

- 邮箱 OTP —— 发送成功语义、验证码校验通过/拒绝、identity 标记已验证
- 微信登录 —— 配置缺失返回 503、微信错误码、上游失败 502、unionid 优先绑定、openid 用户复用
- 成员角色 —— 拒绝遗留的 `child` 角色值
- 场景模板 —— 启用时幂等创建默认文件夹

**尚未覆盖**：任务状态机全路径、保险箱 session 生命周期、配额并发扣减、邀请码加入流程。

代码规范由 `pyproject.toml` 中的 ruff 配置统一约定（行宽 100、`E/F/I/UP/B/W` 规则集），本地 pre-commit 与 CI 共用同一套判定。

---

## 10. 已知问题

按优先级排列，都是动手前值得知道的：

1. **保险箱 OTP 没有真正发邮件，且把验证码明文返回给前端** —— `app/api/documents.py:265` 的 `# TODO: Send email with OTP code` 尚未实现，响应体里带着 `_dev_otp_code` 字段直接回传验证码（注释里写着 "Remove in production!"）。这意味着**保险箱的"二次验证"目前形同虚设**，任何人拿到 token 就能读保险箱。上线前必须接上邮件发送并删掉该字段。对比之下，账号邮箱验证码（`auth_service.send_email_otp`）是走 SMTP 真发的。
2. **Git 历史中仍残留已泄漏的旧 AppSecret** —— 旧 secret（属于另一个 appid `wx243081c7506dddfd`）已在 GitHub 公开仓库的历史提交里。密钥本身已轮换失效，但历史尚未清理。清理方式见第 11 节。
3. **`db/schema.sql` 已落后于 ORM** —— 缺 `users.region`、`users.last_activity_at` 两列和整张 `vip_subscriptions` 表，且 `memberships.user_id` 的可空性与 ORM 不一致。以 Alembic 迁移为准，`schema.sql` 需要同步。
4. **公告附件是"半实现"** —— 创建时校验了 ≤ 5 个附件 ID，但关联文件的逻辑还是 TODO（`app/api/announcements.py:63`），附件实际上没有挂到公告上。
5. **任务附件未接入** —— `SubmissionCreateRequest.attachment_ids` 字段定义了，但 `submit_task` 端点只取了 `body.note` 传给 service，附件 ID 被丢弃。
6. **对象存储直传未接入** —— `files.storage_key` 字段已在，`create_file` 逻辑已在，但真实的上传链路和签名 URL 下发都还没有；`storage_key` 目前由客户端传入，没有服务端校验。
7. **限流只覆盖了 `/auth`** —— 邀请码 join、验证码等敏感接口在 `next-tasks.md` 里列为已完成，但代码里 `limiter.limit` 只出现在 `app/api/auth.py`，其余接口未加限流。
8. **Dockerfile 缺失** —— 部署脚手架还没做（CI 已有）。
9. **`setup.bat` 用 `venv/`、文档用 `.venv/`** —— 两者都能用，但别混着敲命令。

---

## 11. 安全开发指南

### 密钥管理

| 位置 | 用途 | 是否入库 |
|---|---|---|
| `.env` | 真实配置与密钥 | ❌ 已被 `.gitignore` 排除 |
| `.env.example` | 无密模板，含占位符与说明 | ✅ 应入库 |
| `.githooks/pre-commit` | 提交前密钥扫描 | ✅ 应入库 |
| `.secrets.baseline` | 已审查的误报指纹库 | ✅ 应入库 |

**规则：真实密钥只存在于本地 `.env`。** 需要新增配置项时，先改 `.env.example`（写占位符 + 注释），再改本地 `.env`。

### 三道防线

**第 1 道 —— `.gitignore`**
拦截 `.env`、`.env.*`、`*.env`、私钥与证书文件。`.env.example` 通过 `!.env.example` 显式放行。

**第 2 道 —— 本地 pre-commit 钩子**

```bash
git config core.hooksPath .githooks   # 一次性启用
```

提交时自动执行（`.githooks/pre-commit`）：

1. 拒绝暂存真实 `.env` / 私钥文件
2. `detect-secrets-hook` 扫描暂存内容，比对 `.secrets.baseline`
3. 发现基线之外的新密钥 → **中止提交**

> 注：Windows 上 `pre-commit` 框架依赖 POSIX shell，本项目改用自研的 Python 钩子，原生可用、无额外依赖。

**第 3 道 —— CI**（`.github/workflows/ci.yml`）

| Job | 作用 |
|---|---|
| `secret-scan` | 扫描全部受版本控制的文件，发现新增密钥即失败 |
| `lint` | `ruff check` + `ruff format --check` |
| `test` | `pytest`（SQLite 内存库，无需外部服务） |
| `app-smoke` | 校验 FastAPI 应用可装配、`/v1` 端点数量不低于 60 |

### 误报处理

基线里的 10 条均为已知误报（URL 中的 `user:pass@`、测试用 `test-secret`、文档示例）。若新增扫描项是误报：

```bash
detect-secrets --baseline .secrets.baseline    # 交互式确认后更新基线
```

若**是真密钥**：先到对应平台轮换该凭据，再更新基线。顺序不能反 —— 先轮换，再登记。

### 清理 Git 历史（可选）

已泄漏的 secret 仍在历史提交中。密钥轮换后它已失效，但如需彻底清除：

```bash
pip install git-filter-repo
git filter-repo --path .env.example --invert-paths   # 删除该文件的历史
# 或仅替换其中的密钥值：
git filter-repo --replace-text <(echo '旧密钥==>your_wechat_app_secret')
```

⚠️ 这会**重写全部历史**，需要强推（`git push --force --mirror`）到 GitHub 和 Gitee。所有协作者的本地仓库会与远程断裂，需重新 clone。**请务必先确认无人协作，或提前通知团队。**

> 补充：即便清理了历史，GitHub 的 fork、第三方镜像和爬虫缓存仍可能保留旧内容。所以**轮换密钥才是根本解**，历史清理只解决"表面可见性"。

### 密钥轮换清单

微信小程序 AppSecret：

1. 小程序后台 → 开发管理 → 开发设置 → AppSecret → 重置
2. 更新本地 `.env` 的 `WECHAT_APP_SECRET`
3. 旧 secret 立即失效，任何残留引用会报 `40125 invalid appsecret`

> 注意区分 appid：本项目统一使用 `wx20b921f556e521a3`。历史泄漏的 secret 属于另一个 appid `wx243081c7506dddfd`，若该小程序仍在使用，其 secret 也需单独重置。

---

## 12. 相关文档

| 文件 | 内容 |
|---|---|
| `app-overview.md` | 产品定位、角色权限、MVP 范围、文件限额策略、非目标清单 |
| `next-tasks.md` | 分模块任务清单与完成状态（README 的进度以此为准） |
| `docs/superpowers/specs/2026-05-31-auth-membership-scenario-design.md` | 认证/成员/场景三项修正的设计说明 |
| `docs/superpowers/plans/2026-05-31-*.md` | 上述修正的实施计划 |
| `/docs` (Swagger) | 运行时交互式 API 文档 |
