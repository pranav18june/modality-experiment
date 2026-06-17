from app.models import _col
from dotenv import load_dotenv

load_dotenv()
col = _col()
result = col.delete_many({})
print(f"Deleted {result.deleted_count} participants from the database.")
