from fastapi import APIRouter, HTTPException
from config import TOKENS_API_KEY
from database import contracts_collection, analysis_collection
from bson import ObjectId
from bson.errors import InvalidId
from service.analyze_with_gemini import analyze_contract

router = APIRouter(
    prefix="/analysis",
    tags=["analysis"]
)


@router.post("/analyze/{contract_id}")
async def analyze_contract_endpoint(contract_id: str):
    # Analyze a contract with AI and return insights
    if not TOKENS_API_KEY:
        raise HTTPException(status_code=500, detail="TOKENS_API_KEY is not set in the environment variables.")

    doc = contracts_collection.find_one({"_id": ObjectId(contract_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not doc.get("text_content"):
        raise HTTPException(status_code=400, detail="Contract has no text content to analyze.")

    contracts_collection.update_one({"_id": ObjectId(contract_id)}, {"$set": {"status": "analyzing"}})

    try:
        result = await analyze_contract(contract_id, doc["text_content"])
    except Exception as e:
        # Don't leave the contract stuck in "analyzing" if the AI call or parsing fails
        contracts_collection.update_one({"_id": ObjectId(contract_id)}, {"$set": {"status": "failed"}})
        raise HTTPException(status_code=502, detail=f"Analysis failed: {type(e).__name__}: {e}")

    # analysis.contract_id has a unique index, so upsert to allow re-analyzing a contract
    analysis_collection.replace_one(
        {"contract_id": contract_id},
        result.model_dump(exclude={"id"}),
        upsert=True,
    )
    existing = analysis_collection.find_one({"contract_id": contract_id}, {"_id": 1})
    result.id = str(existing["_id"])

    contracts_collection.update_one({"_id": ObjectId(contract_id)}, {"$set": {"status": "Completed"}})


    return {
        "message": "Contract analyzed successfully",
        "analysis": result.model_dump(),
        "id": result.id
    }


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str):
    try:
        object_id = ObjectId(analysis_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid analysis id")

    analysis = analysis_collection.find_one({"_id": object_id})

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # ObjectId can't be serialized to JSON, so expose it as a string "id"
    analysis["id"] = str(analysis.pop("_id"))

    return {
        "analysis": analysis
    }


@router.get("/")
def list_analysis():
    analysis = []

    for doc in analysis_collection.find({}):
        doc["id"] = str(doc.pop("_id"))
        analysis.append(doc)

    return {
        "all_analysis": analysis
    }


@router.get("/contract/{contract_id}")
async def get_analysis_for_contract(contract_id: str):
    analysis = []

    collection = analysis_collection.find({"contract_id": contract_id})

    for doc in collection:
        doc["id"] = str(doc.pop("_id"))
        analysis.append(doc)


    return {
        "total": len(analysis),
        "analysis": analysis
    }