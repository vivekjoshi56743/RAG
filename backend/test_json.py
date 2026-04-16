from fastapi.encoders import jsonable_encoder
from datetime import datetime
import json

now = datetime.now()
data = {"messages": [{"created_at": now}]}
try:
    print(json.dumps(jsonable_encoder(data)))
except Exception as e:
    print(f"Error with jsonable_encoder: {e}")

