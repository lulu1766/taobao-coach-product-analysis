#!/usr/bin/env bash
# Coach 分析系统一键启动（macOS / Linux，SQLite 免安装版）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Coach 分析系统 - 一键启动（SQLite 免安装版）"
echo "============================================"

if [ ! -d venv ]; then
    echo "[1/3] 创建 Python 虚拟环境 ..."
    python3 -m venv venv
    source venv/bin/activate
    echo "[2/3] 安装依赖 ..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

if [ ! -f db.sqlite3 ]; then
    echo "[3/3] 初始化数据库并导入数据（352 条商品 + LSTM 预测结果）..."
    python manage.py migrate --noinput
    python manage.py loaddata coach_data
fi

echo ""
echo "  启动成功！浏览器访问: http://127.0.0.1:8000/"
echo "  按 Ctrl+C 停止服务"
echo ""
python manage.py runserver 8000
