import datetime
from utils.cache_manager import make_serializable

class HeavyObject:
    def __init__(self):
        self.id = 123
        self.message = 'hello'
        self.big_list = list(range(6000))  # should be omitted per threshold
        self.timestamp = datetime.datetime(2025,9,29,18,30,0)

def test_lightweight_reference_omission():
    obj = HeavyObject()
    result = make_serializable(obj)
    assert 'id' in result and result['id'] == 123
    assert 'message' in result
    assert 'big_list' in result
    # Omitted indicator
    assert isinstance(result['big_list'], str) and 'omitted' in result['big_list']
    assert result['timestamp'] == obj.timestamp.isoformat()
