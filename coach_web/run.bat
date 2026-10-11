@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   Coach 分析系统 - 一键启动（SQLite 免安装版）
echo   首次启动会自动配置环境，请耐心等待
echo ============================================

if not exist venv (
    echo [1/3] 创建 Python 虚拟环境 ...
    py -m venv venv
    call venv\Scripts\activate.bat
    echo [2/3] 安装依赖（使用清华镜像）...
    python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
    call venv\Scripts\activate.bat
)

if not exist db.sqlite3 (
    echo [3/3] 初始化数据库并导入数据（352 条商品 + LSTM 预测结果）...
    python manage.py migrate --noinput
    python manage.py loaddata coach_data
)

echo.
echo   启动成功！浏览器访问: http://127.0.0.1:8000/
echo   按 Ctrl+C 停止服务
echo.
python manage.py runserver 8000
pause
