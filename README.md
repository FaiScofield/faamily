# Family Butler (Backend)

FastAPI + PostgreSQL 的家庭管家后端初始工程骨架。

## 本地启动

1. 启动 PostgreSQL

```bash
docker compose up -d db
```

2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 配置环境变量

```bash
cp .env.example .env
```

4. 初始化数据库表结构

```bash
psql "postgresql://family_butler:family_butler@localhost:5432/family_butler" -f db/schema.sql
```

5. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 目录结构

- app/main.py：FastAPI 入口
- app/core/config.py：配置读取（.env）
- app/db.py：SQLAlchemy engine/session
- db/schema.sql：PostgreSQL DDL（MVP）
