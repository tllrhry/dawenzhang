import os
import re

import pymysql


def required(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise SystemExit(f"Set {name} for the one-time database initialization")
    return value


admin_user = os.environ.get("MYSQL_ADMIN_USER", "root")
admin_host = os.environ.get("MYSQL_ADMIN_HOST", "127.0.0.1")
admin_port = int(os.environ.get("MYSQL_ADMIN_PORT", "3306"))
admin_password = required("MYSQL_ADMIN_PASSWORD")
app_user = os.environ.get("MYSQL_APP_USER", "dawenzhang_app")
app_password = required("MYSQL_APP_PASSWORD")

if not re.fullmatch(r"[A-Za-z0-9_]+", app_user):
    raise SystemExit("MYSQL_APP_USER may contain only letters, numbers, and underscores")

connection = pymysql.connect(
    host=admin_host,
    port=admin_port,
    user=admin_user,
    password=admin_password,
    charset="utf8mb4",
    autocommit=True,
)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS `dawenzhang` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(
            f"CREATE USER IF NOT EXISTS `{app_user}`@'%%' IDENTIFIED BY %s",
            (app_password,),
        )
        cursor.execute(f"GRANT ALL PRIVILEGES ON `dawenzhang`.* TO `{app_user}`@'%'")
finally:
    connection.close()

print(f"Initialized MySQL database dawenzhang and application user {app_user}.")
