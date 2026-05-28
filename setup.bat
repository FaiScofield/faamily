@echo off
chcp 65001 >nul
title Family Butler - 一键启动

echo ════════════════════════════════════════
echo   家庭管家 (Family Butler) 一键启动
echo ════════════════════════════════════════
echo.

:: 1. 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python: 
python --version

:: 2. 自动生成 .env（含随机 JWT_SECRET）
if not exist .env (
    echo [+] 正在生成 .env ...

    :: 生成随机 64 位 hex 密钥
    for /f %%i in ('python -c "import secrets; print(secrets.token_hex(32))"') do set JWT=%%i

    (
        echo APP_ENV=local
        echo DATABASE_URL=sqlite:///./data.db
        echo JWT_SECRET=%JWT%
        echo JWT_ACCESS_TOKEN_EXPIRES_MINUTES=30
        echo JWT_REFRESH_TOKEN_EXPIRES_DAYS=30
        echo ADMIN_USER_IDS=
        echo ONLINE_TIMEOUT_MINUTES=15
    ) > .env
    echo [+] .env 已生成（SQLite 模式，无需 PostgreSQL）
) else (
    echo [*] .env 已存在，跳过
)

:: 3. 创建虚拟环境
if not exist venv (
    echo [+] 正在创建虚拟环境 ...
    python -m venv venv
)
echo [OK] 虚拟环境就绪

:: 4. 安装依赖
echo [+] 正在安装依赖（首次会慢一些，耐心等待）...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo [OK] 依赖安装完成

:: 5. 初始化数据库
echo [+] 正在初始化数据库 ...
python init_db.py
echo [OK] 数据库初始化完成

:: 6. 启动 API
echo.
echo ════════════════════════════════════════
echo  🚀 即将启动服务！
echo ════════════════════════════════════════
echo.
echo  接口文档：http://localhost:8000/docs
echo  健康检查：http://localhost:8000/health
echo.
echo  按 Ctrl+C 停止服务
echo.
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
