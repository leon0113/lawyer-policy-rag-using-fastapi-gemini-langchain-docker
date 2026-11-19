from pymongo import MongoClient
from config import MONGODB_URL


client = MongoClient(MONGODB_URL)
db = client["lawyer_ai"]


# Collections
contracts_collection = db["contracts"]
analysis_collection = db["analysis"]

def init_db():
    # Create indexes for collections if needed
    contracts_collection.create_index("filename", unique=True)
    analysis_collection.create_index("contract_id", unique=True)