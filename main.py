from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import databases
import sqlalchemy
from sqlalchemy.orm import Session

# Database connection
DATABASE_URL = "postgresql://username:password@localhost/dbname"
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

app = FastAPI()

# Dependency
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

# CRUD operations
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
    query = users.select().where(users.c.username == user.username)
    db_user = await database.fetch_one(query)
    if db_user is None or db_user['password'] != user.password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"message": "Login successful"}