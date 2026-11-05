"""只读检查 MySQL 版本、字符集和连接，不创建或删除业务表。"""

import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

from download_data import ROOT


def create_database_engine():
    """共用连接配置；凭据只从本机环境读取，不写入日志。"""
    load_dotenv(ROOT / ".env")
    password = os.environ.get("MYSQL_PASSWORD")
    if not password:
        raise ValueError("未配置 MYSQL_PASSWORD，请先运行 python setup_local.py")
    url = URL.create(
        "mysql+pymysql",
        username=os.getenv("MYSQL_USER", "analyst"),
        password=password,
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3307")),
        database=os.getenv("MYSQL_DATABASE", "olist"),
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)


def check_connection(connection) -> dict:
    row = connection.execute(text("SELECT VERSION(), DATABASE(), @@character_set_database")).one()
    version = str(row[0])
    if "mariadb" in version.lower() or int(version.split(".")[0]) < 8:
        raise ValueError(f"题目要求 MySQL 8.0+，实际连接版本为 {version}")
    return {"version": version, "database": row[1], "charset": row[2]}


def check_database() -> dict:
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            return check_connection(connection)
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(check_database())
