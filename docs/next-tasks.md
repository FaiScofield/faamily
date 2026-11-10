# 接下来要做的任务清单（家庭管家 APP）

> 本文件用于把下一阶段工作拆成可执行的任务列表，方便你逐项推进与验收。
>
> **状态基准：2026-11-10**（后端 63 个 `/v1` 端点 · 18 张表 · 35 个测试用例 · 迁移 head `0003_vault_otp_attempts`）
>
> 勾选项以**代码实际状态**为准，不以历史勾选为准。上一版清单中标记为 `[ ]` 的「CI」「vault session 测试」「schema 一致性」等项实际已完成，本次已更正。

## A. 把云端代码落地并进入版本管理

- [x] 从云端下载源码包：`/workspace/export/faamily-backend.tar.gz` 到 PC 本地
- [x] （可选）从云端下载 Git bundle：`/workspace/export/faamily-backend.bundle`，用于保留提交历史
- [x] 在 PC 本地解压/恢复仓库
- [x] 绑定远程仓库并推送到 GitHub：`https://github.com/FaiScofield/faamily`
- [x] 在 GitHub 上检查：分支为 `main`，文件包含 `app/`、`db/schema.sql`、`README.md`

## B. 本地可运行（开发环境基线）

- [ ] 启动 PostgreSQL（docker compose） — 本机未安装 docker/psql；SQLite 基线已走通，生产/集成环境需补齐
- [x] 创建 Python 虚拟环境并安装依赖（requirements.txt）
- [x] 配置 `.env`（从 `.env.example` 复制）— 模板已无真实密钥
- [x] 初始化数据库（执行 `alembic upgrade head`） — 当前 head: `0003_vault_otp_attempts`
- [x] 启动 API 服务并通过 `/health` 验证 — 返回 `{"status":"ok","env":"local"}`，`/openapi.json` 正常

## C. 数据库与迁移体系（避免后期返工）

- [x] 引入 Alembic 迁移（把 `db/schema.sql` 迁移为可追踪的版本）
- [x] 关键字段约束/索引审视 — 25 个索引，`family_id` 维度复合索引齐全，软删除过滤 6 处
- [x] `db/schema.sql` 与 ORM 对齐 — 补齐 `vip_subscriptions` 表、`users.region` 等
- [x] schema 一致性自动校验 — `scripts/check_schema_sync.py`，已接入 CI
- [x] 补齐 0001 迁移遗漏的 `updated_at` 列（4 张表）
- [x] 设计配额扣减/回收策略并落地（上传完成扣减、删除回收、并发保护）

## D. M1 账号与身份（FastAPI）

- [x] 统一用户模型：`users` + `user_identities`（SQLAlchemy ORM）
- [x] 登录方式（按优先级）
  - [x] 游客：创建匿名用户并发放 token
  - [x] 邮箱：注册/登录/验证邮箱
  - [x] 微信小程序：支持 `openid` + `unionid` 绑定（能拿到 unionid 时优先绑定）
- [x] JWT（access/refresh）签发与刷新
- [ ] 补齐限流策略 —— 当前仅 `/auth` 与 `/vault/*` 有限流，**邀请码 join、成员添加等敏感接口未覆盖**

## E. M2 家庭体系（家庭 / 成员 / 邀请码）

- [x] 创建家庭：创建 `families` 并自动创建 `memberships(role=owner)`
- [x] 成员管理：列成员、改角色（owner/admin/member）、移除成员
- [x] 邀请码：生成/作废/过期/次数限制，加入家庭校验与 `used_count` 更新
- [x] 权限中间件：所有 family 资源访问必须校验 membership
- [ ] 审计动作补齐 —— `member.joined`、`announcement.created` 定义了但未实际写入

## F. M3 任务（指派 → 提交 → 验收）

- [x] 任务 CRUD：创建/查询（按 assignee/status/due 过滤）/更新/软删除
- [x] 状态机：`pending → in_progress → submitted → done / rejected`
- [x] 提交与验收
  - [x] assignee 提交材料进入 `submitted`
  - [x] reviewer 通过/驳回，驳回需原因
- [ ] 任务附件：复用统一文件上传（签名直传）与条数/大小限制
  - 当前 `SubmissionCreateRequest.attachment_ids` 字段已定义但端点未使用，附件被丢弃
- [ ] 任务状态机测试 —— 状态流转全路径尚无用例覆盖

## G. M4 公告 + 文档库（shared + vault）+ 二次验证

- [x] 公告：创建/列表/置顶/软删除
- [ ] 公告附件关联 —— 后端 `announcements.py` 仍为 TODO，附件未真正挂到公告上
- [x] 文档库
  - [x] 文件夹：`folders(zone=shared|vault)`，支持层级
  - [x] 文件：`files` 元数据、对象存储 key、权限校验
- [x] 保险箱二次验证（邮箱 OTP）— **2026-11-10 修复**
  - [x] 请求 OTP（邮件真实投递 + 存 hash，响应体不含验证码）
  - [x] 校验 OTP → 创建 `vault_session`（短时有效）
  - [x] 访问 vault 资源强制校验 `vault_session`（省略 `zone` 无法绕过）
  - [x] 失败次数上限（5 次）、邮箱归属校验、旧码作废
- [x] 审计日志：关键动作写入 `audit_logs`

## H. 预设场景（模板化、配置驱动）

- [x] 场景模板表：`scenario_templates`（key/version/definition）
- [x] 启用场景：创建 `scenario_instances`，并初始化默认结构
- [x] 第一批模板
  - [x] 儿童学习 · 老人照护 · 婴儿照看 · 大件归档
  - [x] 宠物照料（第五个模板，代码中已有，清单漏记）

## I. 质量与交付

- [x] CI（lint + 测试 + 密钥扫描 + schema 一致性）— `.github/workflows/ci.yml`，4 个 job
- [x] 单元测试与接口测试 —— 35 个用例（鉴权/OTP/vault session/场景幂等/角色校验）
- [x] 本地密钥扫描钩子 — `.githooks/pre-commit` + `.secrets.baseline`
- [ ] OpenAPI 文档规范化 —— 50 个路径中 **0 个**定义了 `responses` 错误码；36 个路由有 `response_model`
- [ ] 部署脚手架 —— Dockerfile + 生产配置模板

## J. 小程序前端（当前最大的缺口）

后端能力已就位，但小程序端有大量功能未接入：

- [ ] **公告模块** — 后端 5 个端点，小程序 **0 处调用**
- [ ] **文档库 / 保险箱** — 后端 8 个端点，小程序仅首页一个 toast 占位（「文档功能即将上线」）
- [ ] **场景启用交互** — 小程序只能展示模板与启用状态，无法点击启用（`POST /families/{id}/scenarios` 未调用）
- [ ] **VIP 订阅** — 仅只读 `/vip/status`，无订阅/取消入口
- [ ] **管理后台** — 后端 7 个统计端点，小程序无页面（可考虑做 Web 后台而非小程序内）
- [ ] **文件上传** — 全项目无 `wx.uploadFile` / `chooseMessageFile`，附件能力无法落地
