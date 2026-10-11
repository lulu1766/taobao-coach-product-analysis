@echo off
chcp 65001 >nul
cd /d %~dp0
rem 本机使用 MySQL 模式（密码仅本地演示环境，MySQL 仅监听 127.0.0.1）
set USE_MYSQL=1
set DB_PASSWORD=123456
echo ============================================
echo   Coach 商品数据分析可视化系统 启动中...
echo   浏览器访问: http://127.0.0.1:8000/
echo   后台管理:   http://127.0.0.1:8000/admin/
echo   按 Ctrl+C 可停止服务
echo ============================================
py manage.py runserver 8000
pause
