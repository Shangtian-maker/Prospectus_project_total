from pydantic import BaseModel

class Subscription(BaseModel):
    公司: str
    事件类型: str
    数量: float
    页码: int

class Transfer(BaseModel):
    公司: str
    事件类型: str
    数量: str
    页码: int

def validate(subscription, transfer):
    valid_sub = []
    valid_tran = []

    for s in subscription:
        try:
            valid_sub.append(Subscription(
                公司=s["公司"],
                事件类型=s["事件类型"],
                数量=s["数量（万股）"],
                页码=s["页码"]
            ))
        except:
            pass

    for t in transfer:
        try:
            valid_tran.append(Transfer(**t))
        except:
            pass

    return valid_sub, valid_tran