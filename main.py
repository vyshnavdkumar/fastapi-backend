import os
import requests
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import List
import databases
import sqlalchemy
from sqlalchemy.orm import Session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI()

# Keycloak Configuration
KEYCLOAK_URL = "http://localhost:8080"
CLIENT_ID = "atma"
CLIENT_SECRET = "Bi14h4qadgKIMGZXpivFziOS3GQPyY9S"
REALM = "atma"

# Database Configuration
DATABASE_URL = "postgresql://postgres:1234@localhost:5432/postgres"
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Define users table
users = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String),
    sqlalchemy.Column("username", sqlalchemy.String, unique=True),
    sqlalchemy.Column("password", sqlalchemy.String),
)

engine = sqlalchemy.create_engine(DATABASE_URL)
metadata.create_all(engine)

# Pydantic models
class UserIn(BaseModel):
    name: str
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    username: str

class UserUpdate(BaseModel):
    name: str
    username: str

# Dependency for Database Session
def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Keycloak Token Functions
def get_token(username: str, password: str) -> dict:
    data = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": username,
        "password": password
    }
    response = requests.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token", data=data)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")

def introspect_token(token: str) -> dict:
    data = {
        "token": token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token/introspect", data=data)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token introspection failed")

# CRUD Operations
@app.post("/users/", response_model=UserOut)
async def create_user(user: UserIn, db: Session = Depends(get_db)):
    query = users.insert().values(**user.dict())
    last_record_id = await database.execute(query)
    return {**user.dict(), "id": last_record_id}

@app.get("/users/", response_model=List[UserOut])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    query = users.select().offset(skip).limit(limit)
    return await database.fetch_all(query)

@app.get("/users/{user_id}", response_model=UserOut)
async def read_user(user_id: int, db: Session = Depends(get_db)):
    query = users.select().where(users.c.id == user_id)
    user = await database.fetch_one(query)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    query = users.update().where(users.c.id == user_id).values(**user.dict())
    await database.execute(query)
    return {**user.dict(), "id": user_id}

@app.delete("/users/{user_id}", response_model=UserOut)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    query = users.delete().where(users.c.id == user_id)
    await database.execute(query)
    return {"id": user_id, "name": "", "username": ""}

@app.post("/login/")
async def login(user: UserIn, db: Session = Depends(get_db)):
    # Optionally authenticate with your database first
    query = users.select().where(users.c.username == user.username)
    db_user = await database.fetch_one(query)
    if db_user is None or db_user['password'] != user.password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # Then get the Keycloak token
    token = get_token(user.username, user.password)
    return {"access_token": token}

# Token Introspection Endpoint
@app.post("/introspect")
async def introspect(token: str) -> dict:
    token_info = introspect_token(token)
    return token_info

# Logout Endpoint
@app.post("/logout")
async def logout(refresh_token: str) -> str:
    data = {
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/logout", data=data)
    if response.status_code == 204:
        return "Logout Successfully"
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

# Refresh Token Endpoint
@app.post("/refresh-token")
async def refresh_token(refresh_token: str):
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    response = requests.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token", data=data)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

# Custom OpenAPI Documentation
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="ATMA API",
        version="1.0.0",
        description="API Documentation for ATMA Contacts API Endpoints",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    openapi_schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
