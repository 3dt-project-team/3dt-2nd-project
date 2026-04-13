import json
import os
from azure.storage.blob import BlobServiceClient

cs = os.environ.get("STORAGE_CONNECTION_STRING", "").strip()
if not cs:
    raise RuntimeError("STORAGE_CONNECTION_STRING is required")

container_name = os.environ.get("RAW_CONTAINER", "raw").strip() or "raw"
folder_path = os.environ.get("FOLDER_PATH", "news/bing/").strip() or "news/bing/"
if not folder_path.endswith("/"):
    folder_path += "/"

container = BlobServiceClient.from_connection_string(cs).get_container_client(container_name)

months = []
y, m = 2025, 4
while (y < 2026) or (y == 2026 and m <= 4):
    months.append(f'{y}-{m:02d}')
    m += 1
    if m == 13:
        y, m = y + 1, 1

for mm in months:
    yy, mo = mm.split('-')
    path = f'{folder_path}{mm}/bing_news_{yy}_{mo}.json'
    blob = container.get_blob_client(path)
    if not blob.exists():
        print(mm, 'MISSING')
        continue
    rows = len(json.loads(blob.download_blob().readall()))
    print(mm, rows)
