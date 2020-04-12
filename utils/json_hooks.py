from datetime import datetime

### De-serialize & re-serialize datetime objects for JSON storage
def dateconverter(o):
    if isinstance(o, datetime):
        return o.__str__()

def dateparser(dct):
    for k, v in dct.items():
        try:
            dct[k] = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except:
            pass
    return dct

### Get int keys !
def int_keys(ordered_pairs):
    result = {}
    for key, value in ordered_pairs:
        try:
            key = int(key)
        except ValueError:
            pass
        result[key] = value
    return result
