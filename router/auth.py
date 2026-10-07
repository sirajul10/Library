from fastapi import FastAPI, APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Annotated, Optional
from datetime import timedelta, datetime, timezone
from database import SessionLocal, engine
from models import Users
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import JWTError, jwt

router = APIRouter()

bcrypt_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

OAuth2_bearer = OAuth2PasswordBearer(tokenUrl="login")

SECRET_KEY = "8e484fb160b3165eac1f581dd8b7a873f91920d45e3ff37bdad93523d71427c0"
ALGORITHM = "HS256"


class CreateUsers(BaseModel):
    email: str
    username: str
    firstname: str
    lastname: str
    password: str
    role: str

class UpdateUser(BaseModel):
    email: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    firstname: Optional[str] = Field(default=None)
    lastname: Optional[str] = Field(default=None)


class Uppass(BaseModel):
    current_password: str
    new_password: str


def create_access_token(
    username: str,
    user_id: int,
    role: str,
    expires_delta: timedelta
):
    encode = {
        "sub": username,
        "id": user_id,
        "role": role
    }

    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({"exp": expires})

    return jwt.encode(
        encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_current_user(
    token: Annotated[str, Depends(OAuth2_bearer)]
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("sub")
        id = payload.get("id")
        role = payload.get("role")

        if username is None or id is None:
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials"
            )

        return {
            "username": username,
            "id": id,
            "role": role
        }

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def authinticateUser(username, password, db):
    user = db.query(Users).filter(
        Users.username == username
    ).first()

    if user is None:
        return False

    if bcrypt_context.verify(password, user.hash_password):
        return user

    return False


db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


@router.post("/createuser")
def create_users(
    db: db_dependency,
    new_user: CreateUsers
):
    user_model = Users(
        email=new_user.email,
        username=new_user.username,
        firstname=new_user.firstname,
        lastname=new_user.lastname,
        hash_password=bcrypt_context.hash(new_user.password),
        is_active=True,
        role=new_user.role
    )

    db.add(user_model)
    db.commit()

    return JSONResponse(
        status_code=201,
        content={"message": "user added success"}
    )


@router.post("/login")
def login(
    db: db_dependency,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authinticateUser(
        form_data.username,
        form_data.password,
        db
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User Not Found"
        )

    token = create_access_token(
        user.username,
        user.id,
        user.role,
        timedelta(days=1)
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.get("/user")
def getuser(user:user_dependency,db:db_dependency):
    if user is None:
        raise HTTPException(status_code=401,detail="User Not Found")
    current_user = db.query(Users).filter(Users.id == user.get('id')).first()
    if current_user is None:
        raise HTTPException(status_code=401,detail="User is not authenticate")

    return {
       'id':current_user.id,
       'email':current_user.email,
       'username':current_user.username,
       'firstname':current_user.firstname,
       'lastname':current_user.lastname,
       'role' : current_user.role,
       'is_active':current_user.is_active

    }

@router.put("/updateuser")
def Update_User(
    user: user_dependency,
    db: db_dependency,
    update_user: UpdateUser
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Please Login First"
        )

    upuser = db.query(Users).filter(
        Users.id == user.get("id")
    ).first()

    if upuser is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    update_data = update_user.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(upuser, key, value)

    db.commit()

    return JSONResponse(
        status_code=200,
        content={"message": "user Updated successfully"}
    )


@router.put("/passwordchange")
def update_password(
    user: user_dependency,
    db: db_dependency,
    update_password: Uppass
):
    db_user = db.query(Users).filter(
        Users.id == user.get("id")
    ).first()

    if db_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # THIS WAS THE INDENTATION ERROR
    if not bcrypt_context.verify(
        update_password.current_password,
        db_user.hash_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Wrong Password"
        )

    db_user.hash_password = bcrypt_context.hash(
        update_password.new_password
    )

    db.commit()

    return JSONResponse(
        status_code=200,
        content={"message": "Password updated successfully"}
    )