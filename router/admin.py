from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from typing import Annotated,Optional
from datetime import datetime,timedelta,timezone
from database import SessionLocal,engine
from models import Users,Books,Reservations,IssueRecords
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm,OAuth2PasswordBearer
from router.auth import get_current_user,get_db

class CreateBooks(BaseModel):
    title:str
    author:str
    category:str
    description:str = Field(default="",max_length=200)
    price:float = Field(default=0.0,gt=0) 
    total_copies:int = Field(default=1) 

class BookUpdate(BaseModel):
    title:Optional[str] = Field(default=None)
    author:Optional[str] = Field(default=None)
    category:Optional[str] = Field(default=None)
    description:Optional[str] = Field(default=None)
    price:Optional[float] =Field(default=None)
    total_copies:Optional[int] = Field(default=None)
    available_copies:Optional[int] = Field(default=None)

class IssueBook(BaseModel):
     book_id:int
     user_id:int

router = APIRouter()

db_dependency = Annotated[Session,Depends(get_db)]
user_dependency = Annotated[dict,Depends(get_current_user)]
FINE_AMOUNT =20

def fine_calculate(return_date:datetime,due_date:datetime):
    overdue_days = (return_date.date() - due_date.date()).days
    if overdue_days>0:
        return round(overdue_days*FINE_AMOUNT,2)
    else:
        return 0.0

@router.post("/admin/createbook")
def create_book(user:user_dependency,db:db_dependency,newbook:CreateBooks):
    if user is None or user.get('role') !='admin':
        raise HTTPException(status_code=401,detail='You are not eligible for adding books')
    newmodel = Books(
        **newbook.model_dump(),
        available_copies=newbook.total_copies
    )
    db.add(newmodel)
    db.commit()

    return JSONResponse(status_code=201,content={'message':'Book added succssfull'})

@router.put("/admin/updatebook/{book_id}")
def update_book(user:user_dependency,db:db_dependency,updatebook:BookUpdate,book_id:int):
    if user is None or user.get('role') !='admin':
        raise HTTPException(status_code=401,detail='You are not eligible for adding books')
    
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404,detail="Book Not Found")

    updatedata = updatebook.model_dump(exclude_unset=True)
    for key,value in updatedata.items():
        setattr(book,key,value)
    
    db.commit()

    return JSONResponse(status_code=201,content={'message':'Book Updated succssfull'})


@router.delete("/admin/deletebook/{book_id}")
def update_book(user:user_dependency,db:db_dependency,book_id:int):
    if user is None or user.get('role') !='admin':
        raise HTTPException(status_code=401,detail='You are not eligible for adding books')
    
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404,detail="Book Not Found")

    db.query(Books).filter(Books.id == book_id).delete()
    
    db.commit()

    return JSONResponse(status_code=201,content={'message':'Book Deelted succssfull'})


@router.post('/admin/create_issue')
def issue_book(user: user_dependency, db: db_dependency, newIssue: IssueBook):
    if user is None or user.get('role') != 'admin':
        raise HTTPException(status_code=401, detail='Unauthenticated')

    # Lock the book row to avoid race conditions
    book = db.query(Books).filter(Books.id == newIssue.book_id).with_for_update().first()
    if book is None:
        raise HTTPException(status_code=404, detail='Book Not Found')

    member = db.query(Users).filter(Users.id == newIssue.user_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail='User Not Found')

    # Block users with unpaid fines
    unpaid = db.query(IssueRecords).filter(
        IssueRecords.user_id == newIssue.user_id,
        IssueRecords.fine_paid == False,
        IssueRecords.fine_amount > 0
    ).first()
    if unpaid:
        raise HTTPException(status_code=400, detail='User has unpaid fines')

    if book.available_copies <= 0:
        raise HTTPException(status_code=400, detail='No copies Available')

    existing_issue = db.query(IssueRecords).filter(
        IssueRecords.book_id == newIssue.book_id,
        IssueRecords.user_id == newIssue.user_id,
        IssueRecords.status == 'issued'
    ).first()
    if existing_issue:
        raise HTTPException(status_code=400, detail='User already has this book')

    # If someone else has a pending reservation, block
    other_reservation = db.query(Reservations).filter(
        Reservations.book_id == newIssue.book_id,
        Reservations.status == 'pending',
        Reservations.user_id != newIssue.user_id
    ).first()
    if other_reservation:
        raise HTTPException(status_code=400, detail='Book reserved by another user')

    loan_days = 14
    issue_date = datetime.now(timezone.utc)

    issue_model = IssueRecords(
        book_id=newIssue.book_id,
        user_id=newIssue.user_id,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=loan_days),
        status='issued'
    )

    book.available_copies -= 1

    reservation = db.query(Reservations).filter(
        Reservations.book_id == newIssue.book_id,
        Reservations.user_id == newIssue.user_id,
        Reservations.status == 'pending'
    ).first()
    if reservation:
        reservation.status = 'approved'

    try:
        db.add(issue_model)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Failed to issue book: {e}')

    return JSONResponse(status_code=201, content={'message': 'Book issued successfully'})

    
@router.put('/admin/return_book/{issue_id}')
def return_book(user:user_dependency,db:db_dependency,issue_id:int):

    if user is None or user.get('role') !='admin':
        raise HTTPException(status_code=401,detail='Unauthenticated')

    issue = db.query(IssueRecords).filter(IssueRecords.id ==issue_id).first()
    if issue is None:
        raise HTTPException(status_code=401,detail="Issue record Not found")
    
    
    issue.return_date = datetime.now
    issue.status = 'returned'
    issue.fine_amount = fine_calculate(issue.due_date,datetime.now)

    book = db.query(Books).filter(issue.book_id == Books.id).first()
    if book is not None:
        book.available_copies +=1

    db.commit()

    return JSONResponse(status_code=200,content={'message':'Book Retur success','Fine Amount':fine_calculate(issue.due_date,datetime.now)})


@router.put('/admin/fine/paid/{issue_id}')
def fine_paid(user:user_dependency,db:db_dependency,issue_id:int):

    if user is None or user.get('role') !='admin':
        raise HTTPException(status_code=401,detail='Unauthenticated')

    issue = db.query(IssueRecords).filter(IssueRecords.id ==issue_id).first()
    if issue is None:
        raise HTTPException(status_code=401,detail="Issue record Not found")
    
    issue.fine_paid = True

    db.commit()

    return JSONResponse(status_code=200,content={'message':'Fine Paid Successfull'})

