from fastapi import FastAPI,HTTPException,Query,Depends
from sqlalchemy.orm import Session
from typing import Annotated,Optional
import models
from models import Users,Books,Reservations,IssueRecords
from database import SessionLocal,engine
from fastapi.responses import JSONResponse
from router import admin,auth
from router.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware



models.Base.metadata.create_all(bind=engine)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(admin.router)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session,Depends(get_db)]
user_dependency = Annotated[dict,Depends(get_current_user)]

@app.get("/books/all")
def get_all_books( db:db_dependency):
    # if user is None:
    #     raise HTTPException(status_code=401,detail="Faild Authentication")
    books = db.query(Books).all()
    return books

@app.get("/books/{book_id}")
def get_specific(user:user_dependency, db:db_dependency,book_id:int):
    if user is None:
        raise HTTPException(status_code=401,detail="Faild Authentication")
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404,detail='Book Not Found')
    return book

@app.post('/reserve/{book_id}')
def book_reservation(user:user_dependency, db:db_dependency,book_id:int):
    if user is None:
        raise HTTPException(status_code=401,detail="Faild Authentication")
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404,detail='Book Not Found')
    reservation_model = Reservations(
        book_id = book_id,
        user_id = user.get('id'),
        status = 'pending'
    )
    db.add(reservation_model)
    db.commit()
    return JSONResponse(status_code=201,content={'message':'Reservation Added Successfull'})


@app.delete('/reserve/cancel/{reservation_id}')
def book_reservation(
    user: user_dependency,
    db: db_dependency,
    reservation_id: int
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Failed Authentication"
        )

    reservation = (
        db.query(Reservations)
        .filter(Reservations.id == reservation_id)
        .first()
    )

    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail="Reservation Not Found"
        )

    reservation.status = "cancelled"

    db.commit()

    return JSONResponse(
        status_code=200,
        content={"message": "Reservation cancelled successfully"}
    )


@app.get('/reserve/my')
def my_reservation(
    user: user_dependency,
    db: db_dependency
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Failed Authentication"
        )

    reservation = (
        db.query(Reservations)
        .filter(Reservations.user_id == user.get('id'),Reservations.status != "cancelled")
        .all()
    )

    return reservation

@app.get('/issue/my')
def my_reservation(user:user_dependency, db:db_dependency):
    if user is None:
        raise HTTPException(status_code=401,detail="Faild Authentication")
    issues = db.query(IssueRecords).filter(
        IssueRecords.user_id == user.get('id'),
        IssueRecords.status =='issued'
    ).all()

    return issues
