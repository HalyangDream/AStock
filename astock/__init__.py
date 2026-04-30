"""astock 包：多数据源股票 / 基金基础函数库。

对外推荐使用顶层门面（自动多源 fallback）：
    from astock import stock, fund

也可按需直接导入某个源：
    from astock.sina import stockApi as sinaStock
    from astock.eastmoney import fundApi as emFund
"""

from . import stock
from . import fund
from . import eastmoney
from . import sina
from . import tencent

__all__ = ["stock", "fund", "eastmoney", "sina", "tencent"]
