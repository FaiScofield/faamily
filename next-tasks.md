# 接下来要做的任务清单（家庭管家 APP - 后端优先）

> 本文件用于把下一阶段工作拆成可执行的任务列表，方便你逐项推进与验收。

## A. 把云端代码落地并进入版本管理

- [x] 从云端下载源码包：`/workspace/export/faamily-backend.tar.gz` 到 PC 本地
- [x] （可选）从云端下载 Git bundle：`/workspace/export/faamily-backend.bundle`，用于保留提交历史
- [x] 在 PC 本地解压/恢复仓库
  - 源码包：解压后得到工程目录
  - bundle：`git clone /path/to/faamily-backend.bundle .`
- [x] 绑定远程仓库并推送到 GitHub：`https://github.com/FaiScofield/faamily`
- [x] 在 GitHub 上检查：分支为 `main`，文件包含 `app/`、`db/schema.sql`、`README.md`

## B. 本地可运行（开发环境基线）

- [ ] 启动 PostgreSQL（docker compose）
- [ ] 创建 Python 虚拟环境并安装依赖（requirements.txt）
- [ ] 配置 `.env`（从 `.env.example` 复制）
- [ ] 初始化数据库（执行 `alembic upgrade head`）
- [ ] 启动 API 服务并通过 `/health` 验证

## C. 数据库与迁移体系（避免后期返工）

- [x] 引入 Alembic 迁移（把 `db/schema.sql` 迁移为可追踪的版本）
- [ ] 为关键字段补充一致性约束/索引审视（family_id 维度查询、软删除、审计）
- [ ] 设计配额扣减/回收策略并落地（上传完成扣减、删除回收、并发保护）

## D. M1 账号与身份（FastAPI）

- [x] 统一用户模型：`users` + `user_identities`（SQLAlchemy ORM）
- [x] 登录方式（按优先级）
  - [x] 游客：创建匿名用户并发放 token
  - [x] 邮箱：注册/登录/验证邮箱（后续保险箱 OTP 依赖）
  - [x] 微信小程序：支持 `openid` + `unionid` 绑定（能拿到 unionid 时优先绑定）
- [x] JWT（access/refresh）签发与刷新
- [ ] 基础安全：限流策略（邮箱验证码、登录、邀请码 join）

## E. M2 家庭体系（家庭 / 成员 / 邀请码）

- [ ] 创建家庭：创建 `families` 并自动创建 `memberships(role=owner)`
- [ ] 成员管理：列成员、改角色（owner/admin/member/child）、移除成员
- [ ] 邀请码：生成/作废/过期/次数限制，加入家庭校验与 `used_count` 更新
- [ ] 权限中间件：所有 family 资源访问必须校验 membership

## F. M3 任务（指派 → 提交 → 验收）

- [ ] 任务 CRUD：创建/查询（按 assignee/status/due 过滤）/更新/软删除
- [ ] 状态机：`pending → in_progress → submitted → done / rejected`
- [ ] 提交与验收
  - [ ] assignee 提交材料（文字+附件）进入 `submitted`
  - [ ] reviewer 通过/驳回，驳回需原因
- [ ] 任务附件：复用统一文件上传（签名直传）与条数/大小限制

## G. M4 公告 + 文档库（shared + vault）+ 二次验证

- [ ] 公告：创建/列表/置顶/软删除
- [ ] 公告附件：单文件 ≤20MB、每条 ≤5 个
- [ ] 文档库
  - [ ] 文件夹：`folders(zone=shared|vault)`，支持层级
  - [ ] 文件：`files` 元数据、对象存储 key、权限校验
- [ ] 保险箱二次验证（邮箱 OTP）
  - [ ] 请求 OTP（发送邮件 + 存 hash）
  - [ ] 校验 OTP → 创建 `vault_session`（短时有效）
  - [ ] 访问 vault 资源必须携带有效 `vault_session`
- [ ] 审计日志：关键动作写入 `audit_logs`

## H. 预设场景（模板化、配置驱动）

- [ ] 场景模板表：`scenario_templates`（key/version/definition）
- [ ] 启用场景：创建 `scenario_instances`，并初始化默认结构
- [ ] 第一批模板（按你已选）
  - [ ] 儿童学习：重复任务 + 家长验收
  - [ ] 老人照护：用药/复诊提醒 + 紧急联系人
  - [ ] 婴儿照看：喂养/睡眠/尿布/体温记录 + 疫苗/体检提醒
  - [ ] 大件归档：购买记录/保修/说明书/铭牌照片（shared/vault 合理分区）

## I. 质量与交付（建议尽早做）

- [ ] OpenAPI 文档规范化（请求/响应模型、错误码）
- [ ] 单元测试与接口测试（最少覆盖：鉴权、邀请码、任务状态机、vault session）
- [ ] CI（可选）：lint + 测试 + 构建镜像
- [ ] 部署脚手架（可选）：Dockerfile + 生产配置模板
