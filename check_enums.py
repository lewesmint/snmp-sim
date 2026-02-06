import json
from pathlib import Path

problematic = []
for schema_file in Path('mock-behaviour').rglob('schema.json'):
    with open(schema_file) as f:
        schema = json.load(f)
    mib_name = schema_file.parent.name
    for obj_name, obj_info in schema.items():
        if isinstance(obj_info, dict) and 'enums' in obj_info:
            enum_values = set(obj_info['enums'].values())
            initial = obj_info.get('initial')
            if 0 not in enum_values and initial == 0:
                problematic.append(f'{mib_name}::{obj_name} = {initial} (valid: {sorted(enum_values)})')

if problematic:
    print('Found enum fields with invalid 0 default:')
    for p in problematic:
        print(f'  {p}')
else:
    print('No problematic enum defaults found')
