"""运行时数据断言：即使使用 python -O，也必须检查数据不变量。"""


def require(condition, message="数据校验未通过"):
    if not condition:
        raise AssertionError(message)
