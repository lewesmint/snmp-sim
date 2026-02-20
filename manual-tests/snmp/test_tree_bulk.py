import json
import requests

response = requests.get("http://localhost:8800/tree/bulk")
data = response.json()

# Check ifXTable
ifx_oid = "1.3.6.1.2.1.31.1.1"
ifx_table = data.get("tables", {}).get(ifx_oid, {})

print(f"ifXTable: {json.dumps(ifx_table, indent=2)}")
