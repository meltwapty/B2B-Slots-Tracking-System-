import requests
import csv
import io
import json

url = 'https://docs.google.com/spreadsheets/d/1cWZl4-h9YT5TmhhVkfir1uC9TKbqX4PQFBf28vjg5yU/gviz/tq?tqx=out:csv&gid=211400853'
resp = requests.get(url)
reader = csv.reader(io.StringIO(resp.text))
rows = list(reader)

with open('sheet.json', 'w') as f:
    json.dump(rows, f, indent=2)

print("Saved to sheet.json, total rows:", len(rows))
