"""生成本地数据库配置；已有配置不会被覆盖，密码不会打印到终端。"""

import os
import secrets

from download_data import ROOT


def main() -> None:
    path = ROOT / ".env"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print(".env 已存在，保持原样。")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(
            "MYSQL_HOST=127.0.0.1\nMYSQL_PORT=3307\nMYSQL_DATABASE=olist\nMYSQL_USER=analyst\n"
            f"MYSQL_PASSWORD={secrets.token_urlsafe(32)}\n"
            f"MYSQL_ROOT_PASSWORD={secrets.token_urlsafe(32)}\n"
        )
    print("已生成仅本机使用的 .env，文件权限为 600，Git 已忽略。")


if __name__ == "__main__":
    main()
