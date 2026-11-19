from fastapi import APIRouter, UploadFile, File, HTTPException
import os
from uuid import uuid4
from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, UPLOAD_DIR
from service.document_parser import extract_text
from models import Contract
from database import contracts_collection
from bson import ObjectId

router = APIRouter(
    prefix="/contracts",
    tags=["contracts"]
)


@router.post("/upload")
async def upload_contract(
    file: UploadFile = File(...)
):
    # upload a pdf or txt contract for analysis
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and TXT files are allowed.")

    content = await file.read()

    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File size exceeds the maximum limit of {MAX_FILE_SIZE_MB} MB.")
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid4().hex}{ext}"

    file_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(file_path, "wb") as f:
        f.write(content)


    parsed = extract_text(file_path)

    contract_data = Contract(
        filename = unique_name,
        original_name = file.filename,
        text_content = parsed["text"],
        page_count = int(parsed["page_count"]),
        word_count = int(parsed["word_count"]),
    )

    doc = contract_data.model_dump()
    result = contracts_collection.insert_one(doc)
    contract_data.id = str(result.inserted_id)

    return {
        "id": contract_data.id,
        "filename": contract_data.filename,
        "original_name": contract_data.original_name,
        "upload_date": contract_data.upload_date,
        "text_content": contract_data.text_content,
        "page_count": contract_data.page_count,
        "word_count": contract_data.word_count,
        "status": contract_data.status,
    }


@router.get("/")
async def list_contracts():
    # list all uploaded contracts
    contracts = []
    for doc in contracts_collection.find({}, {"text_content": 0}):
        contract = Contract(**doc)
        contract.id = str(doc["_id"])
        contracts.append(contract)

    return contracts


@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    # get a specific contract by id
    doc = contracts_collection.find_one({"_id": ObjectId(contract_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Contract not found")

    contract = Contract(**doc)
    contract.id = str(doc["_id"])
    return contract