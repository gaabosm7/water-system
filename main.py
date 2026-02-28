import os
import shutil
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# ====================================================
# إعدادات قاعدة البيانات - الرابط المطلوب
# ====================================================
SQLALCHEMY_DATABASE_URL = URL.create(
    drivername="postgresql",
    username="postgres.lkefznnqjrktulahptfy",
    password="K4-!_jy#vkV+U9*",
    host="aws-1-ap-northeast-1.pooler.supabase.com",
    port=6543,
    database="postgres"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

os.makedirs("uploads", exist_ok=True)

# ====================================================
# الجداول (Models)
# ====================================================
class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    phone = Column(String, unique=True)
    wallet_balance = Column(Float, default=0.0)

class Meter(Base):
    __tablename__ = "meters"
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    last_reading = Column(Integer, default=0)

class Reading(Base):
    __tablename__ = "readings"
    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id"))
    previous_reading = Column(Integer)
    current_reading = Column(Integer)
    note = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.now)

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    reading_id = Column(Integer, ForeignKey("readings.id"))
    issue_date = Column(DateTime, default=datetime.now)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.now)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    amount = Column(Float)
    expense_date = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

# ====================================================
# التطبيق والعمليات
# ====================================================
app = FastAPI()
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class ReadingInput(BaseModel):
    meter_id: int
    current_reading: int
    note: Optional[str] = None

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.get("/dashboard/")
def get_dashboard(db: Session = Depends(get_db)):
    income = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM payments")).fetchone()[0]
    exp = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM expenses")).fetchone()[0]
    debts = db.execute(text("SELECT COALESCE(SUM(ABS(wallet_balance)), 0) FROM customers WHERE wallet_balance < 0")).fetchone()[0]
    return {"balance": income - exp, "income": income, "expenses": exp, "debts": debts}

@app.get("/customers/")
def get_customers(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.id).all()

@app.get("/users_report/")
def get_users_report(db: Session = Depends(get_db)):
    sql = text("""
        SELECT c.full_name, m.serial_number, m.id as meter_id,
        COALESCE(r.previous_reading, 0) as prev_r, 
        COALESCE(r.current_reading, 0) as curr_r,
        COALESCE(i.amount, 0) as last_amount,
        c.wallet_balance
        FROM customers c
        JOIN meters m ON c.id = m.customer_id
        LEFT JOIN (SELECT DISTINCT ON (meter_id) * FROM readings ORDER BY meter_id, id DESC) r ON r.meter_id = m.id
        LEFT JOIN invoices i ON i.reading_id = r.id
    """)
    return [dict(row) for row in db.execute(sql).mappings()]

@app.post("/readings/")
def add_reading(item: ReadingInput, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == item.meter_id).first()
    if item.current_reading <= meter.last_reading:
        raise HTTPException(status_code=400, detail="القراءة يجب أن تكون أكبر من السابقة")
    
    prev = meter.last_reading
    new_r = Reading(meter_id=item.meter_id, previous_reading=prev, current_reading=item.current_reading, note=item.note)
    db.add(new_r)
    db.commit()
    db.refresh(new_r)
    
    # حساب المبلغ (سعر الوحدة الافتراضي 100)
    amt = (item.current_reading - prev) * 100 
    inv = Invoice(customer_id=meter.customer_id, reading_id=new_r.id, amount=amt)
    db.add(inv)
    
    cust = db.query(Customer).filter(Customer.id == meter.customer_id).first()
    cust.wallet_balance -= amt
    meter.last_reading = item.current_reading
    db.commit()
    return {"message": "تمت العملية"}
