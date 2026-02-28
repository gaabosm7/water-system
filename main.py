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
# 1. إعدادات قاعدة البيانات (الرابط الجديد ☁️)
# استخدمنا URL.create لضمان قراءة الرموز (#, !) في كلمة السر
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
# 2. الجداول (Models)
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

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True)
    value = Column(String)

Base.metadata.create_all(bind=engine)

# ====================================================
# 3. التطبيق والإعدادات
# ====================================================
app = FastAPI()
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# Schemas
class ReadingInput(BaseModel):
    meter_id: int
    current_reading: int
    note: Optional[str] = None

@app.get("/")
async def read_index():
    return FileResponse('index.html')

# ====================================================
# 4. العمليات (APIs)
# ====================================================

@app.get("/dashboard/")
def get_dashboard(db: Session = Depends(get_db)):
    payments = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM payments")).fetchone()[0]
    expenses = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM expenses")).fetchone()[0]
    debts = db.execute(text("SELECT COALESCE(SUM(ABS(wallet_balance)), 0) FROM customers WHERE wallet_balance < 0")).fetchone()[0]
    return {
        "balance": payments - expenses,
        "income": payments,
        "expenses": expenses,
        "debts": debts
    }

@app.get("/customers/")
def get_customers(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.id).all()

@app.post("/readings/")
def add_reading(item: ReadingInput, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == item.meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    if item.current_reading <= meter.last_reading:
        raise HTTPException(status_code=400, detail="القراءة يجب أن تكون أكبر من السابقة")
    
    prev = meter.last_reading
    new_r = Reading(meter_id=item.meter_id, previous_reading=prev, current_reading=item.current_reading, note=item.note)
    db.add(new_r)
    db.commit()
    db.refresh(new_r)

    price_setting = db.execute(text("SELECT value FROM system_settings WHERE key='unit_price'")).fetchone()
    u_price = float(price_setting[0]) if price_setting else 100.0
    amt = (item.current_reading - prev) * u_price

    inv = Invoice(customer_id=meter.customer_id, reading_id=new_r.id, amount=amt)
    db.add(inv)
    cust = db.query(Customer).filter(Customer.id == meter.customer_id).first()
    cust.wallet_balance -= amt
    meter.last_reading = item.current_reading
    db.commit()
    return {"message": "تمت العملية بنجاح"}
