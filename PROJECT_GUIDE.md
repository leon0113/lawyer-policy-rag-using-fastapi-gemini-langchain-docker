# Lawyer AI – Complete Project Guide

A walkthrough of the whole application, in the order things actually happen, written so you can
re-read it later and build a similar project on your own.

> **What the app does:** you upload a contract (PDF or TXT) → the app extracts its text and stores it
> in MongoDB → you ask an AI model to analyze it → the AI's structured answer (summary, key clauses,
> risks, recommendations) is validated and stored → you can read it back at any time.

---

## Table of contents

1. [The big picture](#1-the-big-picture)
2. [Tech stack – what each piece is and why](#2-tech-stack--what-each-piece-is-and-why)
3. [Project structure](#3-project-structure)
4. [Setup: Docker, `.env`, dependencies, running](#4-setup-docker-env-dependencies-running)
5. [What happens when the server starts](#5-what-happens-when-the-server-starts)
6. [`config.py` – settings from `.env`](#6-configpy--settings-from-env)
7. [`database.py` – the MongoDB connection](#7-databasepy--the-mongodb-connection)
8. [`models.py` – Pydantic models (the shape of your data)](#8-modelspy--pydantic-models-the-shape-of-your-data)
9. [FastAPI basics used in this project](#9-fastapi-basics-used-in-this-project)
10. [Flow 1 – Uploading a contract](#10-flow-1--uploading-a-contract)
11. [Flow 2 – Reading contracts back](#11-flow-2--reading-contracts-back)
12. [Flow 3 – AI analysis (the heart of the project)](#12-flow-3--ai-analysis-the-heart-of-the-project)
13. [Flow 4 – Reading analyses back](#13-flow-4--reading-analyses-back)
14. [Full API reference](#14-full-api-reference)
15. [End-to-end walkthrough with real requests](#15-end-to-end-walkthrough-with-real-requests)
16. [MongoDB / PyMongo cheat sheet](#16-mongodb--pymongo-cheat-sheet)
17. [Bugs we hit while building this (and what they teach)](#17-bugs-we-hit-while-building-this-and-what-they-teach)
18. [Known limitations and improvement ideas](#18-known-limitations-and-improvement-ideas)
19. [Blueprint: building a similar project yourself](#19-blueprint-building-a-similar-project-yourself)
20. [Glossary](#20-glossary)

---

## 1. The big picture

```
                         ┌────────────────────────────────────────────┐
  You (Swagger UI /      │              FastAPI application           │
  curl / a frontend)     │                                            │
        │                │  routes/contracts.py   routes/analysis.py  │
        │  HTTP          │          │                    │            │
        ▼                │          ▼                    ▼            │
  POST /contracts/upload │  service/document_parser   service/analyze_ │
  POST /analysis/analyze │  (PDF/TXT → text)         with_gemini.py   │
  GET  /analysis/...     │          │                    │            │
                         │          │            prompt.py + OpenAI   │
                         │          │            SDK  ───────────────────►  Tokens.bd API
                         │          ▼                    │            │     (OpenAI-compatible)
                         │      database.py (PyMongo)    │            │     runs the LLM
                         └──────────┬────────────────────┘            │     deepseek-v4.1-flash
                                    ▼                                  
                         MongoDB (Docker container)
                         db "lawyer_ai"
                           ├─ contracts   (uploaded files + extracted text)
                           └─ analysis    (AI results)
```

**The two key ideas to remember**

1. **FastAPI is just the "front door".** It receives HTTP requests, calls normal Python functions, and
   turns the return value into JSON.
2. **The AI is just another API call.** You send text in, you get text back. Everything clever is in
   (a) the **prompt** you send, and (b) how you **parse and validate** the answer.

### The request lifecycle in one table

| Step | Where | What happens |
|---|---|---|
| 1 | `POST /contracts/upload` | File is checked, saved to `uploads/`, text extracted, record inserted into MongoDB |
| 2 | `POST /analysis/analyze/{id}` | Text is loaded from MongoDB, wrapped in a prompt, sent to the LLM |
| 3 | Same request | LLM's reply is parsed → validated by Pydantic → saved to the `analysis` collection |
| 4 | `GET /analysis/...` | Saved analysis is read back from MongoDB |

---

## 2. Tech stack – what each piece is and why

| Piece | Role | Why it's used |
|---|---|---|
| **FastAPI** | Web framework | Define API routes with plain Python functions; automatic validation; free interactive docs at `/docs` |
| **Uvicorn** | Web *server* | FastAPI is only the app; Uvicorn actually listens on port 8000. `fastapi dev` starts it for you with auto-reload |
| **Pydantic** | Data validation | Describes the shape of your data (`Contract`, `AnalysisResult`). Rejects data that doesn't match |
| **MongoDB** | Database | Stores JSON-like documents. A great fit because AI output is nested JSON (lists of clauses, risks) |
| **PyMongo** | MongoDB driver | The Python library that talks to MongoDB |
| **Docker** | Runs MongoDB | Run a database without installing it on Windows: `docker compose up -d` |
| **PyPDF2** | PDF reading | Extracts text out of PDF pages |
| **python-dotenv** | Config | Loads secrets from the `.env` file into environment variables |
| **python-multipart** | File uploads | Needed by FastAPI to receive `multipart/form-data` (file upload) requests |
| **openai (SDK)** | Calls the LLM | Tokens.bd is *OpenAI-compatible*, so the official OpenAI library works – we only change the base URL |
| **Tokens.bd** | LLM gateway | One API and one key that gives access to many models (DeepSeek, Claude, Gemini…) |

**The AI model** is set by `CHAT_MODEL` in `.env`. Currently:
`deepseek-ai/deepseek-v4.1-flash-1017` — a *reasoning* model (it "thinks" before answering; this matters,
see [section 12.6](#126-the-reasoning-model-gotcha-max_tokens)).

---

## 3. Project structure

```
lawyer_ai/
├── .env                      ← secrets & settings (NEVER commit; it is in .gitignore)
├── .gitignore
├── docker-compose.yml        ← starts MongoDB in Docker
├── requirements.txt          ← Python packages
├── llm_api.md                ← notes about the Tokens.bd API
├── sample_contract.txt       ← a test contract
├── PROJECT_GUIDE.md          ← this file
├── data/db/                  ← MongoDB's data files (created by Docker, gitignored)
├── uploads/                  ← uploaded contract files are saved here
└── app/
    ├── main.py               ← creates the FastAPI app, registers routers
    ├── config.py             ← reads .env, defines constants
    ├── database.py           ← MongoDB connection, collections, indexes
    ├── models.py             ← Pydantic models (Contract, AnalysisResult, ...)
    ├── routes/
    │   ├── contracts.py      ← /contracts/... endpoints
    │   └── analysis.py       ← /analysis/... endpoints
    └── service/
        ├── document_parser.py   ← PDF/TXT → text
        ├── prompt.py            ← the prompts sent to the AI
        └── analyze_with_gemini.py ← calls the AI + parses the answer
```

**A pattern worth copying – separation of concerns:**

| Layer | Folder | Rule |
|---|---|---|
| **Routes** | `routes/` | Only deal with HTTP: read the request, call a service, return a response, raise HTTP errors |
| **Services** | `service/` | The real work: parsing files, calling the AI. They know nothing about HTTP |
| **Models** | `models.py` | The shape of the data |
| **Infrastructure** | `config.py`, `database.py` | Settings and connections |

> Naming note: `analyze_with_gemini.py` is a historical name. The project originally called Google
> Gemini directly, then switched to Tokens.bd. The file name stayed; it now uses the OpenAI SDK.
> `GEMINI_API_KEY` in `config.py` / `.env` is a leftover and is no longer used.

---

## 4. Setup: Docker, `.env`, dependencies, running

### 4.1 `docker-compose.yml` – the database

```yaml
services:
  mongodb:
    image: mongo:latest          # the official MongoDB image
    container_name: mongodb
    ports:
      - "27017:27017"            # host-port:container-port  → reachable at localhost:27017
    volumes:
      - ./data/db:/data/db       # store the DB files in ./data/db so data survives restarts
    environment:
      MONGO_INITDB_ROOT_USERNAME: root
      MONGO_INITDB_ROOT_PASSWORD: <your password>
```

Line by line:

- `ports: "27017:27017"` – "forward my computer's port 27017 into the container's port 27017". This is why
  your Python app can reach MongoDB at `localhost:27017`.
- `volumes: ./data/db:/data/db` – a container's own files vanish when it's deleted. This maps a folder on
  your disk into the container so the data persists.
- `MONGO_INITDB_ROOT_*` – creates the admin user **only the first time**, when `data/db` is empty. Changing
  these later has no effect on an already-initialized database (you'd have to delete `data/db`).

Commands:

```bash
docker compose up -d        # start MongoDB in the background
docker ps                   # check it's running (look for "mongodb ... Up")
docker compose down         # stop it (data stays in ./data/db)
```

> **If you restart your PC, run `docker compose up -d` again** (or start the container in Docker Desktop).
> A "connection refused" error from the app almost always means the container isn't running.

### 4.2 `.env` – configuration and secrets

```env
TOKENS_API_KEY=tok_live_xxxxxxxx
TOKENS_BASE_URL=https://tokens.bd/v1
CHAT_MODEL=deepseek-ai/deepseek-v4.1-flash-1017

MONGODB_URL=mongodb://root:<password>@localhost:27017/lawyer_ai?authSource=admin
```

**Anatomy of the MongoDB URL**

```
mongodb://root:<password>@localhost:27017/lawyer_ai?authSource=admin
          └─┬┘ └───┬────┘ └───┬───┘ └─┬─┘ └───┬───┘ └──────┬───────┘
          user  password    host   port   database   where the user lives
```

- **host = `localhost`** because your app runs on Windows and Docker publishes the port to Windows.
  The name `mongodb` (the compose service name) only works for *other containers* on Docker's internal
  network – on Windows it gives `getaddrinfo failed` (we hit this exact error).
- **`authSource=admin`** – the `root` user was created in the `admin` database, so MongoDB must check the
  password there, even though you then work in `lawyer_ai`.

**Why a `.env` file?** Secrets and per-machine settings stay out of the code and out of git.

### 4.3 Install and run

```bash
python -m venv venv                 # create an isolated Python environment (once)
venv\Scripts\activate               # activate it (Windows)  | Git Bash: source venv/Scripts/activate
pip install -r requirements.txt     # install packages
docker compose up -d                # start MongoDB
fastapi dev                         # start the API with auto-reload
```

Open <http://127.0.0.1:8000/docs> – FastAPI generates an interactive page where you can try every endpoint.

---

## 5. What happens when the server starts

When you run `fastapi dev`, things happen in this order:

```
1. fastapi dev finds app/main.py and uses  main:app   ("file main.py, variable app")
2. Python imports main.py, which imports (top to bottom):
      database.py   → imports config.py → load_dotenv() reads .env
                     → creates the MongoClient (no connection yet!) + collection objects
      routes/contracts.py → imports document_parser.py, models.py, database.py ...
      routes/analysis.py  → imports analyze_with_gemini.py → creates the AsyncOpenAI client
                                                         → imports prompt.py
3. app = FastAPI(...) is created, routers are registered with include_router
4. Uvicorn starts and runs the "lifespan" startup code → init_db() → creates indexes
   (THIS is the first real MongoDB connection – a bad URL/auth fails *here*)
5. "Application startup complete" – now requests are accepted
```

### `main.py`

```python
from fastapi import FastAPI
from database import init_db
from contextlib import asynccontextmanager
from routes.contracts import router as contracts_router
from routes.analysis import router as analysis_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()        # runs ONCE at startup
    yield            # ← the app serves requests while paused here
                     # (code after yield would run at shutdown)

app = FastAPI(
    title="Lawyer AI API",
    description="An API for Lawyer AI, providing legal assistance and information.",
    lifespan=lifespan
)

app.include_router(contracts_router)
app.include_router(analysis_router)

@app.get("/")
def root():
    return {"message": "App is running!"}
```

What to understand here:

- **`lifespan`** is FastAPI's hook for "do something at startup / shutdown". Everything *before* `yield` runs
  at startup, everything after at shutdown. Use it for connecting to databases, loading models, etc.
- **`include_router`** plugs a group of routes (a `APIRouter`) into the app. This is how you keep a big API
  split across files instead of one giant `main.py`.
- **`@app.get("/")`** is a *decorator*: "when someone sends `GET /`, run this function and send back its
  return value as JSON". A returned `dict` becomes a JSON object.

> **Why `from database import ...` and not `from app.database import ...`?** `fastapi dev` finds
> `app/main.py` and adds the `app/` folder to Python's import path, so sibling files are imported by plain
> name. That's why all imports in this project look like `from config import ...`.

---

## 6. `config.py` – settings from `.env`

```python
from dotenv import load_dotenv
import os

load_dotenv()                                   # read .env into environment variables

MONGODB_URL = os.getenv("MONGODB_URL")

ALLOWED_EXTENSIONS = [".pdf", ".txt"]
MAX_FILE_SIZE_MB = 10
UPLOAD_DIR = "uploads"

TOKENS_API_KEY = os.getenv("TOKENS_API_KEY")
TOKENS_BASE_URL = os.getenv("TOKENS_BASE_URL", "https://tokens.bd/v1")   # 2nd arg = default value
CHAT_MODEL = os.getenv("CHAT_MODEL", "google/gemini-3.8-flash")
```

- `load_dotenv()` copies every `KEY=value` line of `.env` into the process's environment.
- `os.getenv("NAME")` reads one; `os.getenv("NAME", "default")` falls back to a default if it's missing.
  If there's no default and the variable is missing you get `None` (that's why the analyze route checks
  `if not TOKENS_API_KEY`).
- Constants that aren't secret (`ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE_MB`) live here too, so they can be changed
  in one place.
- `UPLOAD_DIR = "uploads"` is **relative to the folder you start the server from** (the project root), so files
  land in `lawyer_ai/uploads/`.

> **Remember:** the `.env` file is read once at startup. After editing it, **restart** `fastapi dev`
> (the auto-reloader only watches code files).

---

## 7. `database.py` – the MongoDB connection

```python
from pymongo import MongoClient
from config import MONGODB_URL

client = MongoClient(MONGODB_URL)       # create the client (does NOT connect yet)
db = client["lawyer_ai"]                # pick a database (created automatically on first write)

# Collections  (≈ tables in SQL)
contracts_collection = db["contracts"]
analysis_collection = db["analysis"]

def init_db():
    contracts_collection.create_index("filename", unique=True)
    analysis_collection.create_index("contract_id", unique=True)
```

### Key concepts

| MongoDB term | SQL equivalent | In this project |
|---|---|---|
| Database | Database | `lawyer_ai` |
| Collection | Table | `contracts`, `analysis` |
| Document | Row | one contract / one analysis (a Python `dict`) |
| `_id` | Primary key | Auto-generated `ObjectId`, e.g. `6aff2e65bafb92d5c74f43d9` |

- **`MongoClient(url)` is lazy.** It doesn't connect until the first real operation. That's why connection
  errors appeared inside `init_db()`, not on the `MongoClient(...)` line.
- **Databases and collections are created automatically** the first time you write to them. No migrations.
- **Indexes.** `create_index("contract_id", unique=True)` tells MongoDB "no two documents may have the same
  `contract_id`". It also makes lookups by that field fast. Running `create_index` repeatedly is safe – if the
  index already exists nothing happens.
  - `analysis.contract_id` unique ⇒ **one analysis per contract**. (This is why the analyze route uses an
    *upsert*, see 12.9.)
  - `contracts.filename` unique ⇒ the stored filename must be unique. Since the app generates a random UUID
    filename for every upload, this never triggers; it's a safety net, not a duplicate-upload check.

### What a stored contract looks like

```json
{
  "_id": "ObjectId('6aff2e65bafb92d5c74f43d9')",
  "id": null,
  "filename": "c32d79299c3c48de995f0c280e7ec602.txt",
  "original_name": "sample_contract.txt",
  "upload_date": "2026-11-19T23:14:13.044382",
  "text_content": "SERVICE AGREEMENT\n\nThis Service Agreement ...",
  "page_count": 61,
  "word_count": 647,
  "status": "uploaded"
}
```

(`"id": null` is a harmless leftover – the `Contract` model has an `id` field that is `None` at insert time;
the real identifier is `_id`.)

---

## 8. `models.py` – Pydantic models (the shape of your data)

A Pydantic model is a Python class that describes data and **validates it automatically**.

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

**`RiskLevel`** is an *Enum*: a fixed list of allowed values. Because it also inherits from `str`, its members
behave like strings (`RiskLevel.HIGH == "high"` is `True`) and are saved to MongoDB / JSON as plain
`"high"`. If the AI ever invents a level like `"severe"`, Pydantic raises a `ValidationError` instead of
silently storing garbage.

```python
class Contract(BaseModel):
    id: Optional[str] = None
    filename: str                 # required (no default)
    original_name: str            # required
    upload_date: str = ""         # optional, default ""
    text_content: str = ""
    page_count: int = 0
    word_count: int = 0
    status: str = "uploaded"

    def model_post_init(self, __context):
        if not self.upload_date:
            self.upload_date = datetime.now().isoformat()
```

- A field **without** a default is **required** (`filename`). Leave it out → `ValidationError`.
- `Optional[str] = None` means "a string or `None`, default `None`".
- Types are **enforced and converted**: passing `page_count="61"` becomes `61`; passing `"abc"` raises.
- `model_post_init` runs right after validation – here it stamps the upload time if none was given.

```python
class ClauseAnalysis(BaseModel):
    clause_title: str
    clause_text: str
    explanation: str
    is_standard: bool

class RiskFlag(BaseModel):
    risk_title: str
    description: str
    risk_level: RiskLevel          # must be one of the four enum values
    recommendation: str
    clause_reference: str = ""

class AnalysisResult(BaseModel):
    id: Optional[str] = None
    contract_id: str
    analysis_date: str = ""
    summary: str = ""
    contract_type: str = ""
    key_clauses: list[ClauseAnalysis] = []     # a LIST of ClauseAnalysis objects
    risk_flags: list[RiskFlag] = []
    overall_risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = []
    ...
```

Models can contain other models. An `AnalysisResult` holds a list of `ClauseAnalysis` and a list of
`RiskFlag`. **These field names are a contract between three places** – keep them identical in:

1. the JSON structure requested in `prompt.py`,
2. these models,
3. the parsing code in `analyze_with_gemini.py`.

### The three Pydantic operations you use constantly

```python
# 1. Create a model from keyword arguments
c = Contract(filename="abc.txt", original_name="deal.txt")

# 2. Create a model from a dict using ** (dict unpacking)
data = {"filename": "abc.txt", "original_name": "deal.txt", "page_count": 3}
c = Contract(**data)            # same as Contract(filename="abc.txt", original_name=..., page_count=3)

# 3. Turn a model back into a plain dict (what MongoDB and JSON need)
c.model_dump()
# {'id': None, 'filename': 'abc.txt', 'original_name': 'deal.txt', 'upload_date': '2026-...', ...}
c.model_dump(exclude={"id"})    # same, without the "id" key
```

> **Why models at all, when you could just use dicts?** A typo in a dict key fails silently later; a model
> fails immediately with a clear message. And the AI's output is *untrusted* input – Pydantic is how you
> verify it.

---

## 9. FastAPI basics used in this project

### 9.1 Routers and path prefixes

```python
router = APIRouter(prefix="/contracts", tags=["contracts"])

@router.post("/upload")            # full path: POST /contracts/upload
@router.get("/")                   # full path: GET  /contracts/
@router.get("/{contract_id}")      # full path: GET  /contracts/<anything>
```

`prefix` is prepended to every route; `tags` only groups them in the `/docs` page.

### 9.2 Path parameters

```python
@router.get("/{contract_id}")
async def get_contract(contract_id: str):    # FastAPI fills contract_id from the URL
    ...
```

`GET /contracts/6aff2e65...` → `contract_id = "6aff2e65..."`. The function parameter name must match
the name in `{braces}`.

### 9.3 File uploads

```python
async def upload_contract(file: UploadFile = File(...)):
```

- `UploadFile` gives you `file.filename` and `await file.read()` (the bytes).
- `File(...)` marks it as a required form file. The **parameter name (`file`) is the form field name** the
  client must use (`curl -F "file=@x.txt"`).
- Needs `python-multipart` installed.

### 9.4 Errors → `HTTPException`

```python
raise HTTPException(status_code=404, detail="Contract not found")
```

Stops the function and sends `{"detail": "Contract not found"}` with that status code. Codes used here:

| Code | Meaning | Used for |
|---|---|---|
| 200 | OK | success |
| 400 | Bad request | wrong file type, too large, invalid ID, no text to analyze |
| 404 | Not found | unknown contract/analysis |
| 422 | Unprocessable | FastAPI's automatic "your input is invalid" (missing/ill-typed parameters) |
| 500 | Server error | an unhandled bug in your code |
| 502 | Bad gateway | the *upstream* service (the AI) failed |

### 9.5 `async def` vs `def` (important)

- **`await`** means "start this slow operation (network call, file read) and let the server handle other
  requests until it finishes". It only works inside `async def`.
- The AI call is `await client.chat.completions.create(...)`, so while one request waits ~1 minute for the
  model, the server remains responsive to others.
- **Caveat:** PyMongo is a *synchronous* library. Inside an `async def` route, a PyMongo call briefly blocks
  the whole server. For a learning project (fast local DB) that's fine. Two cleaner options for bigger apps:
  use plain `def` for routes that only use PyMongo (FastAPI runs those in a thread pool – which is what
  `get_analysis` and `list_analysis` do), or switch to the async driver (`motor` / PyMongo's async API).

### 9.6 Return values become JSON

- Return a `dict` → JSON object.
- Return a Pydantic model (like `Contract`) → FastAPI converts it to JSON.
- Return a list of models → JSON array.
- **Return something JSON can't represent (like a MongoDB `ObjectId`) → 500 error.** See section 17.

---

## 10. Flow 1 – Uploading a contract

`POST /contracts/upload` in `routes/contracts.py`. Here is the whole function, followed by each step.

```python
@router.post("/upload")
async def upload_contract(file: UploadFile = File(...)):
    # 1. validate the extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and TXT files are allowed.")

    # 2. read the file and validate its size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File size exceeds the maximum limit of {MAX_FILE_SIZE_MB} MB.")

    # 3. save the file to disk under a random name
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. extract the text
    parsed = extract_text(file_path)

    # 5. build a validated Contract object
    contract_data = Contract(
        filename = unique_name,
        original_name = file.filename,
        text_content = parsed["text"],
        page_count = int(parsed["page_count"]),
        word_count = int(parsed["word_count"]),
    )

    # 6. save to MongoDB
    doc = contract_data.model_dump()
    result = contracts_collection.insert_one(doc)
    contract_data.id = str(result.inserted_id)

    # 7. respond
    return { "id": contract_data.id, "filename": ..., "original_name": ..., ... }
```

### Follow one real upload: what each step produces

These are **real values** from running the exact upload steps on `sample_contract.txt`. The random parts
(`unique_name`, `upload_date`, `ObjectId`) are different on every run.

```text
You send:   POST /contracts/upload     form field  file = sample_contract.txt

STEP 1  extension check
        os.path.splitext("sample_contract.txt")[1].lower()   →  '.txt'
        '.txt' in ALLOWED_EXTENSIONS ['.pdf', '.txt']          →  True   (continue)

STEP 2  read + size check
        content = await file.read()
        content[:40]                 →  b'SERVICE AGREEMENT\n\nThis Service Agreemen'     (raw bytes)
        len(content)                 →  4118          (bytes)
        size_mb = 4118 / (1024*1024) →  0.00393       (limit is 10)   (continue)

STEP 3  save to disk under a random name
        unique_name = '506c57d3b22243089e93d31a11a9f36d.txt'
        file_path   = 'uploads\506c57d3b22243089e93d31a11a9f36d.txt'
        → the file now exists in lawyer_ai/uploads/

STEP 4  extract_text(file_path)  returns a dict of 3 STRINGS
        {
          'text':       'SERVICE AGREEMENT\n\nThis Service Agreement (the "Agreement") is entered into as of ...',
          'page_count': '61',      ← a string, and for .txt it is really the number of LINES
          'word_count': '647'      ← a string
        }

STEP 5  Contract(...) validates and fills the blanks, then .model_dump() turns it into a dict
        {
          "id": null,                                              ← not known yet
          "filename": "506c57d3b22243089e93d31a11a9f36d.txt",      ← the random name
          "original_name": "sample_contract.txt",                  ← what the user uploaded
          "upload_date": "2026-11-21T19:08:13.713326",             ← added by model_post_init
          "text_content": "SERVICE AGREEMENT\n\nThis Service Agreemen...",   (shortened here)
          "page_count": 61,                                        ← int("61") → 61
          "word_count": 647,                                       ← int("647") → 647
          "status": "uploaded"                                     ← default value
        }

STEP 6  insert_one(doc)
        result.inserted_id           →  ObjectId('6b0197bd52ef67d01651b5ba')    (what MongoDB returns)
        str(result.inserted_id)      →  '6b0197bd52ef67d01651b5ba'              (what you give the client)
        (Mongo also silently added "_id": ObjectId(...) into `doc`)

STEP 7  the JSON the client receives  →  see "Step 7 – the response" below
```

**Why the conversions matter** – look at how the same number changes type along the way:

```text
text.split() → 647 words          (a Python int inside document_parser)
str(...)     → '647'              (document_parser returns strings)
int('647')   → 647                (the route converts back, so Pydantic and MongoDB store a number)
```

### Step 1 – validate the extension

```python
os.path.splitext("My Contract.PDF")     # → ("My Contract", ".PDF")
os.path.splitext("My Contract.PDF")[1]  # → ".PDF"   (index 1 = the extension)
.lower()                                 # → ".pdf"  (so ".PDF" and ".pdf" both work)
```

Cheap rule: never trust the client's file name. (Note this only checks the *name*, not the real content type.)

### Step 2 – read and check the size

`await file.read()` gives raw `bytes`. `len(content)` is the byte count; dividing by `1024 * 1024` converts to
megabytes. The check happens *after* reading, so a huge upload is already in memory – acceptable for 10 MB.

### Step 3 – save under a random name

```python
uuid4().hex            # → 'c32d79299c3c48de995f0c280e7ec602'  (random, 32 chars)
f"{uuid4().hex}{ext}"  # → 'c32d79299c3c48de995f0c280e7ec602.txt'
```

Why not keep the original name? Two users could upload `contract.pdf`, overwriting each other, and
names from users can contain nasty characters (`../../`). The original name is kept separately in
`original_name` for display. `exist_ok=True` means "don't crash if `uploads/` already exists".
`"wb"` = write **b**inary (required for bytes).

### Step 4 – `extract_text` (service/document_parser.py)

```python
def extract_text_from_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return {
        "text": text.strip(),
        "page_count": str(text.count("\n") + 1),      # number of LINES (txt has no pages)
        "word_count": str(len(text.split()))
    }

def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return {
        "text": text.strip(),
        "page_count": str(len(reader.pages)),         # a REAL page count
        "word_count": str(len(text.split()))
    }

def extract_text(file_path):                          # the dispatcher
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    else:
        raise ValueError("Unsupported file type. Only PDF and TXT files are allowed.")
```

- **Dispatcher pattern:** one public function (`extract_text`) picks the right specialised helper. To support
  `.docx` later you'd add one more helper and one more `elif`.
- `text.split()` with no arguments splits on any whitespace, so `len(text.split())` is the word count.
  Example: `"a  b\nc".split()` → `['a', 'b', 'c']` → 3 words.
- `text.count("\n") + 1` = number of lines. This is why a 61-line text file shows `page_count: 61`.
- The values are returned as **strings** (`"61"`), which is why the route converts them with `int(...)`.
- **PDF caveat:** `extract_text()` only works for PDFs with a real text layer. A *scanned* PDF is just
  pictures; you'd get empty text and need OCR.

### Step 5 – build a `Contract`

This is where Pydantic validates: required fields are present, `page_count` is an integer, and
`model_post_init` fills in `upload_date` automatically.

### Step 6 – insert into MongoDB

```python
doc = contract_data.model_dump()                 # model → dict
result = contracts_collection.insert_one(doc)    # store it
contract_data.id = str(result.inserted_id)       # ObjectId → string
```

- `insert_one` returns an object whose `.inserted_id` is the new document's `_id`.
- It is an `ObjectId`, not a string, so we convert with `str(...)` before sending it back as JSON.
- ⚠️ **Gotcha:** `insert_one(doc)` *modifies `doc`* by adding an `_id` key containing an `ObjectId`.
  Returning that same `doc` in the response crashed the endpoint (bug #1 in section 17).

### Step 7 – the response

```json
{
  "id": "6aff2e65bafb92d5c74f43d9",
  "filename": "c32d79299c3c48de995f0c280e7ec602.txt",
  "original_name": "sample_contract.txt",
  "upload_date": "2026-11-19T23:14:13.044382",
  "text_content": "SERVICE AGREEMENT\n\n...",
  "page_count": 61,
  "word_count": 647,
  "status": "uploaded"
}
```

**Save the `id`** – you need it to start the analysis.

### What exists after a successful upload

Two things were created, linked by the random file name:

```text
1. A file on disk:
      lawyer_ai/uploads/506c57d3b22243089e93d31a11a9f36d.txt        (an exact copy of what you uploaded)

2. A document in MongoDB   (database lawyer_ai → collection contracts):
      {
        _id:           ObjectId('6b0197bd52ef67d01651b5ba'),      ← added by MongoDB
        id:            null,
        filename:      '506c57d3b22243089e93d31a11a9f36d.txt',     ← points to the file on disk
        original_name: 'sample_contract.txt',
        upload_date:   '2026-11-21T19:08:13.713326',
        text_content:  'SERVICE AGREEMENT\n\nThis Service Agreement ...',   ← the full extracted text
        page_count:    61,
        word_count:    647,
        status:        'uploaded'
      }
```

The AI analysis later uses `text_content` from MongoDB – **not** the file on disk. The file is kept only as an
archive copy.

### What the failures look like

Each `raise HTTPException(...)` becomes a JSON response with that status code. Try these in `/docs`:

```text
Upload "notes.docx"  (or photo.PNG)         → '.docx' / '.png' is not in ['.pdf', '.txt']
  HTTP 400
  {"detail": "Invalid file type. Only PDF and TXT files are allowed."}

Upload a file bigger than 10 MB
  HTTP 400
  {"detail": "File size exceeds the maximum limit of 10 MB."}

Send the request without any file   (the `file` form field is required, so FastAPI rejects it itself –
  HTTP 422                           your function never even runs)
  {"detail": [{"type": "missing", "loc": ["body", "file"], "msg": "Field required", "input": null}]}
```

Note that the extension and size checks happen **before** anything is saved, so a rejected upload leaves no
file in `uploads/` and no record in MongoDB.

---

## 11. Flow 2 – Reading contracts back

```python
@router.get("/")
async def list_contracts():
    contracts = []
    for doc in contracts_collection.find({}, {"text_content": 0}):    # ← projection
        contract = Contract(**doc)
        contract.id = str(doc["_id"])
        contracts.append(contract)
    return contracts

@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    doc = contracts_collection.find_one({"_id": ObjectId(contract_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract = Contract(**doc)
    contract.id = str(doc["_id"])
    return contract
```

Things to notice:

- **`find({}, {"text_content": 0})`** – first argument is the *filter* (`{}` = everything), the second is a
  *projection*: `0` means "exclude this field". A contract's text can be huge, so the list leaves it out
  (it shows as `""`). The single-contract route includes it.
- **`ObjectId(contract_id)`** converts the string from the URL back into the type MongoDB uses for `_id`.
  Searching `{"_id": "6aff..."}` with a plain string finds nothing – the types differ.
- **`find_one` returns `None`** when nothing matches, hence the `if not doc:` → 404.
- **`Contract(**doc)`** unpacks the Mongo dict into a model. The `_id` key is ignored (Pydantic ignores
  unknown keys by default); we then set `contract.id` ourselves from it.
- Returning a `Contract` object (or a list of them) lets FastAPI serialise it for you.

---

## 12. Flow 3 – AI analysis (the heart of the project)

Files involved: `routes/analysis.py` (the endpoint) → `service/analyze_with_gemini.py` (calls the AI) →
`service/prompt.py` (the instructions). Read them in this order.

```
POST /analysis/analyze/{contract_id}
   │
   ├─ 1. check the API key exists
   ├─ 2. load the contract from MongoDB (404 if missing, 400 if no text)
   ├─ 3. set status = "analyzing"
   ├─ 4. call analyze_contract(...)  ─────────────►  build prompt → call LLM → parse → validate
   │        └─ on any error: status = "failed", return 502
   ├─ 5. save the result (upsert) into the "analysis" collection
   ├─ 6. set status = "Completed"
   └─ 7. return the analysis
```

### 12.1 The endpoint (`routes/analysis.py`)

```python
@router.post("/analyze/{contract_id}")
async def analyze_contract_endpoint(contract_id: str):
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
        contracts_collection.update_one({"_id": ObjectId(contract_id)}, {"$set": {"status": "failed"}})
        raise HTTPException(status_code=502, detail=f"Analysis failed: {type(e).__name__}: {e}")

    analysis_collection.replace_one(
        {"contract_id": contract_id},
        result.model_dump(exclude={"id"}),
        upsert=True,
    )
    existing = analysis_collection.find_one({"contract_id": contract_id}, {"_id": 1})
    result.id = str(existing["_id"])

    contracts_collection.update_one({"_id": ObjectId(contract_id)}, {"$set": {"status": "Completed"}})

    return {"message": "Contract analyzed successfully", "analysis": result.model_dump(), "id": result.id}
```

Notes:

- **Why is the function named `analyze_contract_endpoint`?** Because the *service* function is called
  `analyze_contract` and Python lets a later `def` silently replace an earlier import of the same name.
  When both had the same name, the route called *itself* and crashed (bug #4 in section 17).
  **Give route functions and service functions different names.**
- **`doc.get("text_content")`** – `dict.get(key)` returns `None` instead of crashing if the key is missing.
  An empty string is also "falsy", so `not ""` is `True` → 400 (this is what a scanned PDF would hit).
- **`update_one(filter, {"$set": {...}})`** changes only the listed fields. Without `$set`, MongoDB would
  reject the update. `$set` is an *update operator*.
- **The status lifecycle:** `uploaded` → `analyzing` → `Completed` (or `failed`). The `try/except` makes
  sure a crashed analysis can't leave a contract stuck in `analyzing` forever.
- **`except Exception as e` + `raise HTTPException(502, ...)`** converts *any* failure (network problem,
  bad JSON, validation error) into a clean JSON error for the client, including the real reason.

### 12.2 The prompt (`service/prompt.py`)

A prompt is just a long string. This project's `CONTRACT_ANALYSIS_PROMPT` has five parts:

```
1. ROLE          "You are an experienced contract lawyer reviewing a contract for a business reader..."
2. THE INPUT     "CONTRACT TEXT:\n{contract_text}"        ← a placeholder
3. OUTPUT SHAPE  a JSON example showing every field
4. FIELD RULES   "risk_level must be exactly one of: low, medium, high, critical"
5. BEHAVIOUR     "Base everything ONLY on the contract text. Never invent clauses..."
                 "Return ONLY the JSON object. No markdown, no code fences, no other text."
```

**Why each part matters**

| Part | What it prevents |
|---|---|
| Role | Gives the model a consistent point of view and tone |
| Output shape (JSON example) | Without it you get free-form prose you can't store or validate |
| "must be exactly one of…" | The model inventing `"severe"` → Pydantic would reject it |
| "ONLY from the contract text" | **Hallucination** – the model inventing facts. (Our first prompt said "Indian contract law"; the AI then wrote about "Indian parties" in a US contract. The prompt's assumptions leak into the answer!) |
| "Return ONLY the JSON" | Chatty replies like "Sure! Here's the analysis: ..." that break `json.loads` |

**Placeholders and double braces – a classic gotcha.** The prompt is filled in with Python's
`str.format()`. `{contract_text}` is a placeholder; but JSON *also* uses `{` and `}`. Real braces must be
doubled so `format()` leaves them alone:

```python
template = 'Name: {name}. Return {{"ok": true}}'
template.format(name="Ana")
# → 'Name: Ana. Return {"ok": true}'

# If you forget to double the JSON braces:
'Return {"ok": true}'.format(name="Ana")
# → KeyError: '"ok"'      ← Python thinks {"ok": true} is a placeholder
```

The file also contains three more prompts (`CLAUSE_EXTRACTION_PROMPT`, `RISK_ASSESSMENT_PROMPT`,
`SUMMARY_PROMPT`). The app only uses the first today – the others are ready if you want to split the analysis
into several smaller AI calls.

### 12.3 The client: calling an OpenAI-compatible API

```python
from openai import AsyncOpenAI
from config import TOKENS_API_KEY, TOKENS_BASE_URL, CHAT_MODEL

client = AsyncOpenAI(
    base_url=TOKENS_BASE_URL,            # "https://tokens.bd/v1"  ← instead of OpenAI's server
    api_key=TOKENS_API_KEY or "missing", # the SDK refuses to be created with None
    timeout=180.0,                       # give up on a single attempt after 180 seconds
)
```

- **"OpenAI-compatible"** means the provider copies OpenAI's request/response format. So the official
  `openai` library works with *any* such provider – you only change `base_url`, `api_key` and the model
  name. Learn this once, use it with many providers.
- **`AsyncOpenAI`** is the `async` flavour, so we can `await` it without blocking the server.
- The client is created **once at import time** and reused – cheaper than creating one per request.
- The SDK **retries automatically** (default 2 retries) on network errors and 5xx errors, so we don't write
  our own retry loop. (This also means one slow request can take longer than `timeout`: attempt 1 times out,
  attempt 2 runs.)
- The API key is sent in an `Authorization: Bearer <key>` header by the SDK. **Never put it in frontend
  code** – call the AI only from your backend.

### 12.4 The call itself

```python
prompt = CONTRACT_ANALYSIS_PROMPT.format(contract_text=text_content[:15000])

response = await client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=16000,
    temperature=0.2,
)
```

| Piece | Meaning |
|---|---|
| `text_content[:15000]` | Slice: only the first 15,000 characters (~2,500 words). Protects against huge inputs, but **longer contracts are silently cut off** |
| `model` | Which LLM to use (`CHAT_MODEL` from `.env`) |
| `messages` | The conversation. Each message has a `role` (`system` = rules, `user` = your input, `assistant` = the model's replies) and `content` (text). We send a single `user` message that contains everything |
| `max_tokens` | Upper limit on the length of the **reply**. A *token* is roughly ¾ of a word |
| `temperature` | Randomness, 0–1+. **Low (0.2) = focused and repeatable** – right for analysis. High = creative – right for stories |

The shape of what comes back:

```python
response.choices[0].message.content    # the model's text answer  ← what we want
response.choices[0].finish_reason      # "stop" (finished normally) or "length" (hit max_tokens)
response.usage.prompt_tokens           # tokens you sent    (you pay for these)
response.usage.completion_tokens       # tokens it produced (you pay for these too)
```

The code prints `Tokens usage: prompt=1645 completion=7627` – a handy way to watch cost.

### 12.5 Handling the reply: `_extract_json`

LLMs are *supposed* to return pure JSON, but sometimes wrap it in a Markdown code fence or add a sentence
before it. `_extract_json` is defensive parsing:

```python
def _extract_json(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)   # remove an opening ``` or ```json
    raw_text = re.sub(r"\s*```$", "", raw_text).strip()    # remove a closing ```
    try:
        return json.loads(raw_text)                        # normal case
    except json.JSONDecodeError:
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end <= start:
            raise                                          # nothing JSON-like → re-raise the error
        return json.loads(raw_text[start:end + 1])         # cut out from first { to last }
```

**Three examples of what it handles**

```text
(a) Clean:          {"summary": "A contract..."}
    → json.loads works straight away.

(b) Code fence:     ```json
                    {"summary": "A contract..."}
                    ```
    → the two re.sub lines strip the fences, leaving {"summary": ...}.

(c) Chatty:         Sure! Here is the analysis: {"summary": "A contract..."} Hope it helps!
    → json.loads fails → find("{") and rfind("}") locate the object → slice it out → parse.
```

Regex pieces explained:

| Pattern | Reads as |
|---|---|
| `^` and `$` | start / end of the text |
| `` ``` `` | three literal backticks |
| `(?:json)?` | optionally the word `json` (`?:` = group without capturing) |
| `\s*` | any amount of whitespace (spaces, newlines) |

Other details: a bare `raise` inside `except` re-raises the *original* error. `str.find()` returns `-1` when
nothing is found, and `rfind` searches from the right – so `{` at the first position to `}` at the last.

### 12.6 The reasoning-model gotcha: `max_tokens`

```python
choice = response.choices[0]
if not choice.message.content:
    raise RuntimeError(f"Empty response from model (finish_reason={choice.finish_reason})")
```

`deepseek-v4.1-flash` is a **reasoning model**: before answering it generates hidden "thinking" tokens, and
those **count toward `max_tokens`**. With `max_tokens=4000` it spent everything on thinking, hit the limit
and returned **empty content with `finish_reason="length"`**. We raised it to `16000` and added this check so
an empty reply gives a clear error instead of a confusing crash later.

Rule of thumb: **reasoning models need a generous `max_tokens`** (≥ 1000 minimum; much more for long answers).

### 12.7 Validate with Pydantic – never trust the AI's output

```python
analysis_data = _extract_json(choice.message.content)        # a plain dict now

key_clauses = [
    ClauseAnalysis(**clause)
    for clause in analysis_data.get("key_clauses", [])
]
risk_flags = [
    RiskFlag(**risk)
    for risk in analysis_data.get("risk_flags", [])
]

result = AnalysisResult(
    contract_id=contract_id,
    summary=analysis_data.get("summary", ""),
    contract_type=analysis_data.get("contract_type", "Unknown"),
    key_clauses=key_clauses,
    risk_flags=risk_flags,
    overall_risk_level=analysis_data.get("overall_risk_level", "low"),
    recommendations=analysis_data.get("recommendations", []),
)
return result
```

Unpacking the list comprehension with an example:

```python
analysis_data = {"key_clauses": [
    {"clause_title": "Payment", "clause_text": "The Client shall pay ...",
     "explanation": "Fixed installments", "is_standard": False},
]}

[ClauseAnalysis(**clause) for clause in analysis_data.get("key_clauses", [])]
#   for each dict in the list:  ClauseAnalysis(**dict)  →  ClauseAnalysis(clause_title="Payment", ...)
# → [ClauseAnalysis(clause_title='Payment', ..., is_standard=False)]
```

- `.get("key_clauses", [])` returns an empty list if the AI left that key out, so we don't crash.
- If a clause is **missing a required field** (say no `explanation`) or has `risk_level: "severe"`,
  Pydantic raises `ValidationError`. The route's `except Exception` catches it → status `failed` + 502.
- `"critical"` (a string from the JSON) is automatically converted to `RiskLevel.CRITICAL`.
- Anything extra the AI adds is ignored.

### 12.8 Saving: upsert

```python
analysis_collection.replace_one(
    {"contract_id": contract_id},              # find the doc for this contract...
    result.model_dump(exclude={"id"}),         # ...replace it with the new analysis
    upsert=True,                               # ...or insert it if none exists
)
existing = analysis_collection.find_one({"contract_id": contract_id}, {"_id": 1})
result.id = str(existing["_id"])
```

**Upsert = update + insert.** Because `analysis.contract_id` is unique, a plain `insert_one` on the second
analysis of the same contract would fail with a `DuplicateKeyError`. With upsert, re-analyzing a contract
*replaces* the old result. `{"_id": 1}` is a projection: "return only the `_id`" – we only need it to give the
client the analysis id.

### 12.9 What the finished analysis looks like

```json
{
  "message": "Contract analyzed successfully",
  "id": "6aff49ca7abbafbd8b1f9f72",
  "analysis": {
    "id": "6aff49ca7abbafbd8b1f9f72",
    "contract_id": "6aff2e65bafb92d5c74f43d9",
    "analysis_date": "2026-11-20T01:11:06.932594",
    "summary": "This is a six-month Service Agreement under which ...",
    "contract_type": "Service Agreement",
    "key_clauses": [
      {
        "clause_title": "Warranty Disclaimer and Liability Cap",
        "clause_text": "The Contractor provides the Services \"as is\" ...",
        "explanation": "The Contractor gives no quality warranties and is liable for at most $500 ...",
        "is_standard": false
      }
    ],
    "risk_flags": [
      {
        "risk_title": "Extremely low liability cap",
        "description": "The Contractor's total liability is capped at $500 ...",
        "risk_level": "critical",
        "recommendation": "Negotiate a liability cap tied to fees paid ...",
        "clause_reference": "Section 6.2"
      }
    ],
    "overall_risk_level": "critical",
    "recommendations": ["Do not sign as drafted; ...", "..."]
  }
}
```

### 12.10 Practical notes about calling an LLM

- **It's slow.** Each analysis takes ~45–60 seconds normally, occasionally minutes (reasoning models vary).
  The HTTP request stays open that whole time.
- **It costs money per token** (input + output). Log `usage` as the code does.
- **It's not deterministic.** Even at low temperature the wording differs between runs.
- **It can be wrong.** Always show the result as *assistance*, not as legal advice.
- **Errors you may see** (the route puts them in the 502 message):

| Error | Meaning | What to do |
|---|---|---|
| `401 Invalid API key` | Wrong/placeholder key in `.env` | Fix `TOKENS_API_KEY`, restart the server |
| `402 insufficient_credits` | Out of credit | Top up; don't retry |
| `404 / 403 model_not_found` | Wrong `CHAT_MODEL` id | Check the model list from `GET /v1/models` |
| `429 rate_limited` | Too many requests | Wait and retry later |
| `503 temporarily unavailable` | The provider's model is down | Retry, or switch `CHAT_MODEL` |
| `Empty response ... finish_reason=length` | `max_tokens` too low for a reasoning model | Raise `max_tokens` |
| `JSONDecodeError` | Model didn't return valid JSON | Tighten the prompt, or retry |
| `ValidationError` | JSON was valid but didn't match the models | Check prompt field names vs `models.py` |

---

## 13. Flow 4 – Reading analyses back

```python
@router.get("/{analysis_id}")
def get_analysis(analysis_id: str):
    try:
        object_id = ObjectId(analysis_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid analysis id")

    analysis = analysis_collection.find_one({"_id": object_id})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis["id"] = str(analysis.pop("_id"))      # ObjectId → string, under the key "id"
    return {"analysis": analysis}


@router.get("/")
def list_analysis():
    analysis = []
    for doc in analysis_collection.find({}):
        doc["id"] = str(doc.pop("_id"))
        analysis.append(doc)
    return {"all_analysis": analysis}


@router.get("/contract/{contract_id}")
async def get_analysis_for_contract(contract_id: str):
    analysis = []
    for doc in analysis_collection.find({"contract_id": contract_id}):
        doc["id"] = str(doc.pop("_id"))
        analysis.append(doc)
    return {"total": len(analysis), "analysis": analysis}
```

- **The key line is `doc["id"] = str(doc.pop("_id"))`.** `dict.pop("_id")` *removes* the `_id` key and returns
  its value; we convert it to a string and store it under `id`. After this, the dict contains no `ObjectId`,
  so FastAPI can turn it into JSON. This is the standard recipe for returning Mongo documents.
- `ObjectId("not-valid")` raises `InvalidId`; we catch it and return 400 instead of letting it become a 500.
- `/contract/{contract_id}` finds the analysis *by contract* (more convenient than remembering the analysis id).
- **Route order:** `/{analysis_id}` matches only a *single* path segment, so it can't swallow
  `/contract/abc` (two segments). In general put fixed paths (`/upload`) **before** parameter paths
  (`/{id}`) when they share a method and prefix, or the parameter route will grab them.
- These are plain `def` (not `async def`) because they only use the synchronous PyMongo – FastAPI runs them in
  a worker thread so they don't block the server.

---

## 14. Full API reference

| Method | Path | Purpose | Success | Common errors |
|---|---|---|---|---|
| GET | `/` | Health check | `{"message": "App is running!"}` | – |
| POST | `/contracts/upload` | Upload a PDF/TXT (form field `file`) | contract JSON with `id` | 400 bad type/too large |
| GET | `/contracts/` | List contracts (without text) | array | – |
| GET | `/contracts/{contract_id}` | One contract incl. text | contract JSON | 404 |
| POST | `/analysis/analyze/{contract_id}` | Run the AI analysis | analysis JSON | 404, 400 no text, 502 AI failed |
| GET | `/analysis/` | List all analyses | `{"all_analysis": [...]}` | – |
| GET | `/analysis/{analysis_id}` | One analysis | `{"analysis": {...}}` | 400 bad id, 404 |
| GET | `/analysis/contract/{contract_id}` | Analysis for a contract | `{"total": n, "analysis": [...]}` | – |

Interactive docs: <http://127.0.0.1:8000/docs> · Alternative docs: <http://127.0.0.1:8000/redoc>

---

## 15. End-to-end walkthrough with real requests

Start Docker and the server first (`docker compose up -d`, then `fastapi dev`).

**Step 1 – upload** (Git Bash / macOS / Linux; on Windows use the `/docs` page if `curl` quoting is awkward):

```bash
curl -X POST http://127.0.0.1:8000/contracts/upload \
     -F "file=@sample_contract.txt"
```

`file=@path` means "send this file in the form field named `file`" – the same name as the parameter in
`upload_contract(file: UploadFile)`. Copy the returned `"id"`.

**Step 2 – analyze** (takes about a minute):

```bash
curl -X POST http://127.0.0.1:8000/analysis/analyze/6aff2e65bafb92d5c74f43d9
```

**Step 3 – read it back:**

```bash
curl http://127.0.0.1:8000/analysis/contract/6aff2e65bafb92d5c74f43d9
curl http://127.0.0.1:8000/analysis/
curl http://127.0.0.1:8000/contracts/
```

**Check what's in MongoDB directly** (great for understanding what is stored):

```bash
docker exec -it mongodb mongosh -u root -p <password> --authenticationDatabase admin
> use lawyer_ai
> db.contracts.find({}, {text_content: 0})
> db.analysis.find().pretty()
> db.contracts.countDocuments()
```

**What the test contract (`sample_contract.txt`) contains:** it's a fictional service agreement with
deliberately one-sided clauses (a $500 liability cap, a 5-year worldwide non-compete, auto-renewal with a
10% price increase, 2% monthly late interest…) so you can check whether the AI finds them.

---

## 16. MongoDB / PyMongo cheat sheet

Every operation this project uses:

| Operation | Code | Meaning |
|---|---|---|
| Insert one | `col.insert_one(doc)` → `.inserted_id` | Add a document |
| Find one | `col.find_one({"_id": ObjectId(x)})` | First match, or `None` |
| Find many | `col.find({"contract_id": x})` | A cursor you can loop over |
| Find all | `col.find({})` | Empty filter = everything |
| Exclude a field | `col.find({}, {"text_content": 0})` | Projection: `0` = leave out |
| Only some fields | `col.find_one({...}, {"_id": 1})` | Projection: `1` = include only |
| Update fields | `col.update_one(filter, {"$set": {"status": "x"}})` | Change specific fields |
| Replace / upsert | `col.replace_one(filter, newdoc, upsert=True)` | Replace whole doc, or insert if absent |
| Count | `col.count_documents({})` | Number of matches |
| Index | `col.create_index("field", unique=True)` | Speed up lookups / enforce uniqueness |

Rules of thumb:

- **Filters are dicts:** `{"field": value}`. Several keys = AND.
- **`_id` is an `ObjectId`**, never a plain string: wrap with `ObjectId(...)` when querying, and `str(...)`
  when sending it out.
- **Operators start with `$`:** `$set`, `$gt`, `$in`, …
- A *cursor* (from `find`) is lazy; loop over it or wrap it in `list(...)`.

---

## 17. Bugs we hit while building this (and what they teach)

Real errors from this project – recognising them will save you hours.

| # | Symptom | Root cause | Fix | Lesson |
|---|---|---|---|---|
| 1 | `getaddrinfo failed` for host `mongodb` at startup | `.env` used the Docker *service name* `mongodb` as host, but the app runs on Windows, outside Docker's network | Use `localhost` in `MONGODB_URL` | Hostnames from `docker-compose.yml` only work *between containers* |
| 2 | `Authentication failed` | URL user was `admin` but the compose file creates user `root` | Use `root` | `.env` credentials must match what the DB container was created with |
| 3 | `WinError 10053` right after restarting Docker | App connected while MongoDB was still booting | Wait a few seconds, restart the app | "Container is Up" ≠ "database is ready" |
| 4 | `'ObjectId' object is not iterable` (500 on upload) | `insert_one(doc)` adds `_id: ObjectId` to `doc`, and the response included `doc` | Don't return the raw dict / pop `_id` | `ObjectId` is not JSON; convert with `str()` |
| 5 | `page_count` and `word_count` always `1` | The parser returned counts as strings like `"647"`; the route then ran `.split()` on them (one token → length 1) | `int(parsed["word_count"])` | Check the *type* of values flowing between functions |
| 6 | `analyze_contract() takes 1 positional argument but 2 were given` | A route function and an imported service function had the **same name**; the later `def` replaced the import | Rename the route to `analyze_contract_endpoint` | Never reuse a name in the same file |
| 7 | Request hung for minutes with the direct Gemini call | Service issues on that setup (bare test script also hung) | Switched to Tokens.bd | Always test an external API in isolation with a timeout |
| 8 | `503 This model is temporarily unavailable` | The provider's model was down | Retry or switch `CHAT_MODEL` | External services fail; surface their error text |
| 9 | `401 Invalid API key` | Placeholder/old key in `.env` | Put the real key, restart | `.env` changes need a server restart |
| 10 | `Empty response ... finish_reason=length` | Reasoning model used the whole `max_tokens` on thinking | `max_tokens` 4000 → 16000 | Reasoning tokens count against `max_tokens` |
| 11 | AI mentioned "Indian parties" for a US contract | Prompt said "specializing in Indian contract law" (copied from elsewhere) | Rewrote the prompt to be jurisdiction-neutral | The AI obeys *your* assumptions – audit copied prompts |
| 12 | `422 analysis_id Field required` on the list route | An unused function parameter becomes a **required query parameter** | Delete the parameter | In FastAPI every parameter is part of the API |
| 13 | Contract stuck in `analyzing` after a failure | Status set before the AI call, never reset on error | `try/except` → status `failed` | Always clean up state on failure |
| 14 | Possible `DuplicateKeyError` on re-analysis | Unique index on `analysis.contract_id` + plain `insert_one` | `replace_one(..., upsert=True)` | Match your write operation to your unique indexes |

**General debugging habit that solved all of these:** read the *last* line of the traceback first (the actual
error), then walk *up* to the first line that is in *your* code (`app/...`), ignoring the library frames.

---

## 18. Known limitations and improvement ideas

Being honest about what a learning project doesn't do yet – each is a good next exercise.

**Correctness / robustness**

- **Invalid IDs on some routes return 500.** `get_contract` and the analyze route call `ObjectId(contract_id)`
  without the `try/except InvalidId` that `get_analysis` has. Make a small helper
  (`def parse_object_id(value): ...`) and reuse it.
- **Long contracts are silently truncated** at 15,000 characters (`text_content[:15000]`). Either raise the
  limit (check the model's context window), warn the user, or split into chunks.
- **`.txt` files must be UTF-8**; another encoding crashes with `UnicodeDecodeError` (a 500).
- **`.txt` "page count" is the number of lines.** A better estimate is `max(1, round(word_count / 500))`.
- **Orphaned files:** if parsing fails after the file is saved, the file stays in `uploads/`. Delete it in an
  `except` block.
- **Status values are inconsistent** (`Completed` is capitalised, the others aren't). Use an `Enum`.
- **Sync PyMongo inside `async def` routes** blocks the event loop briefly (see 9.5).
- `contracts.filename` unique index never triggers (UUID names). To prevent re-uploading the *same file*,
  store a hash of the content (`hashlib.sha256(content).hexdigest()`) and make *that* unique.

**Security**

- **No authentication.** Anyone who can reach the server can read every contract. Add login (OAuth2/JWT)
  before real use.
- **`uploads/` is not in `.gitignore`** – it holds uploaded contracts. Add `uploads/` to `.gitignore`.
- **The MongoDB password is hard-coded** in `docker-compose.yml` (and the URL in `.env`). Move it to
  `.env` and reference it in compose, and never expose port 27017 publicly.
- Uploaded contracts are sent to a third-party LLM provider. For real clients' documents, check the
  provider's data-handling terms.

**Product / performance**

- **A 1-minute request is awkward.** Better: return `202 Accepted` immediately, run the analysis with
  FastAPI `BackgroundTasks` (or a queue like Celery/RQ), and let the client poll
  `GET /contracts/{id}` for the status.
- **Use a `system` message** for the rules and a `user` message for the contract (cleaner, and gives better
  adherence on some models).
- Try **`response_format={"type": "json_object"}`** if your provider supports it – it forces valid JSON.
- Add **pagination** to the list routes (`find().skip(n).limit(m)`).
- Add **tests** (`pytest` + FastAPI's `TestClient`) – mock the LLM so tests are free and fast.
- Add **DELETE** endpoints, and use the unused prompts (clause extraction → risk assessment) to build a
  multi-step pipeline.
- Add **logging** (`import logging`) instead of `print`.
- Rename `analyze_with_gemini.py` → `analyze_with_llm.py` and remove the unused `GEMINI_API_KEY`.

---

## 19. Blueprint: building a similar project yourself

This app is a template for **"upload a document → AI extracts structured data → store it → query it"**.
The same skeleton works for resumes, invoices, medical reports, support tickets, meeting notes, etc.

### The recipe

1. **Write down the data flow first** – input, steps, output. (e.g. *resume PDF → text → AI → skills/experience JSON → DB*.)
2. **Design the output shape** (the JSON you want from the AI) and write it as **Pydantic models** *before*
   anything else. Decide enums for any fixed vocabulary (`RiskLevel`).
3. **Set up infrastructure:** `docker-compose.yml` for the DB, `.env` for secrets, `config.py` to read them,
   `database.py` for the client + collections + indexes.
4. **Write the document parser** as an independent function. Test it on its own in a Python shell.
5. **Write the prompt** with: role → input placeholder → JSON example → field rules → behaviour rules →
   "return only JSON". Keep field names identical to the models.
6. **Write the AI service function** `async def analyze(...)`: format the prompt → call the API → check for
   empty/length problems → parse JSON defensively → validate with Pydantic → return the model.
   **Test it in isolation** with a small script and a timeout before wiring it into FastAPI.
7. **Write the routes**: validate input, call the service, save to the DB, convert `ObjectId`s, wrap the
   AI call in `try/except` and update a status field.
8. **Register routers** in `main.py`, run `fastapi dev`, and try everything in `/docs`.
9. **Add the read routes** (list/get) and handle bad IDs and "not found".
10. **Harden:** limits, logging, auth, tests, background processing.

### A minimal skeleton to start from

```python
# models.py
from pydantic import BaseModel
class Result(BaseModel):
    doc_id: str
    summary: str = ""
    items: list[str] = []

# service/ai.py
import json
from openai import AsyncOpenAI
client = AsyncOpenAI(base_url="https://<provider>/v1", api_key="<key>", timeout=180)

PROMPT = """Summarize the text and list the key items.
TEXT:
{text}

Return ONLY JSON: {{"summary": "...", "items": ["...", "..."]}}"""

async def analyze(doc_id: str, text: str) -> Result:
    r = await client.chat.completions.create(
        model="<model>", temperature=0.2, max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.format(text=text[:15000])}],
    )
    content = r.choices[0].message.content
    if not content:
        raise RuntimeError(f"Empty response ({r.choices[0].finish_reason})")
    data = json.loads(content)                       # use a defensive parser in real code
    return Result(doc_id=doc_id, **data)             # Pydantic validates the AI's output

# routes/docs.py
from fastapi import APIRouter, HTTPException
router = APIRouter(prefix="/docs-ai")

@router.post("/analyze/{doc_id}")
async def analyze_route(doc_id: str):
    ...load text from DB, 404 if missing...
    try:
        result = await analyze(doc_id, text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")
    ...save result, return it...
```

### Habits that make AI projects work

- **Test the AI call in a tiny standalone script first.** Isolate network, key and model problems from your app.
- **Treat AI output as untrusted input.** Parse defensively, validate with a schema, handle failure.
- **Put the AI's rules in the prompt, and verify them in code.** The prompt says "risk_level must be one of
  four values"; the Enum *enforces* it.
- **Log token usage and timing** from day one.
- **Keep prompts in their own file** so you can tune them without touching logic.

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **API / endpoint / route** | A URL + HTTP method that runs a function (e.g. `POST /contracts/upload`) |
| **HTTP methods** | GET = read, POST = create/do something, PUT/PATCH = update, DELETE = remove |
| **JSON** | Text format for data: objects `{}`, lists `[]`, strings, numbers, `true/false/null` |
| **Status code** | Number in the response: 2xx success, 4xx you sent something wrong, 5xx the server failed |
| **Decorator** (`@router.get`) | Wraps a function to register it as a route |
| **Pydantic model** | A class describing + validating data |
| **Enum** | A fixed set of allowed values |
| **`**dict` unpacking** | `f(**{"a": 1})` is the same as `f(a=1)` |
| **async / await** | Lets the server do other work while waiting on slow I/O |
| **Environment variable** | A named setting outside the code (`.env` → `os.getenv`) |
| **MongoDB document / collection** | A JSON-like record / a group of records (≈ row / table) |
| **ObjectId** | MongoDB's default `_id` type (not a string, not JSON-serialisable) |
| **Index** | A lookup structure; `unique=True` also forbids duplicates |
| **Projection** | Choosing which fields a query returns |
| **Upsert** | Update if it exists, otherwise insert |
| **LLM** | Large Language Model – the AI that turns your prompt into text |
| **Prompt** | The instructions + data you send to the LLM |
| **Token** | A chunk of text (~¾ word). Limits and prices are measured in tokens |
| **`max_tokens`** | Maximum tokens the model may generate in its reply |
| **`temperature`** | Randomness of the reply (low = consistent) |
| **Reasoning model** | An LLM that thinks step by step first; thinking tokens count toward `max_tokens` |
| **Hallucination** | The model stating things that aren't true or aren't in the source |
| **OpenAI-compatible API** | Any provider that copies OpenAI's request/response format, so the `openai` SDK works with it |
| **Docker volume** | A folder shared between your PC and a container so data persists |
| **Lifespan** | FastAPI hook for code that runs at app startup/shutdown |
