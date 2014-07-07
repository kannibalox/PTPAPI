import re
import json

def snarf_cover_view_data(text):
    data = []
    for d in re.finditer(r'coverViewJsonData\[\s*\d+\s*\]\s*=\s*({.*});', text):
        data.extend(json.loads(d.group(1))['Movies'])
    return data