import os

# 仅在使用 MySQL 时加载 pymysql 驱动，SQLite 零依赖模式不需要
if os.environ.get('USE_MYSQL') == '1':
    import pymysql
    pymysql.install_as_MySQLdb()
