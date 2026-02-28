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
# ====================================================
SQLALCHEMY_DATABASE_URL = URL.create(
    drivername="postgresql",
    username="postgres.lkefznnqjrktulahptfy",
    password="K4-!_jy#vkV+U9*", 
    host="aws-1-ap-northeast-1.pooler.supabase.com", # الرابط الجديد هنا
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
    note = Column(String, nullable=True) # حقل الملاحظات
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
    image_path = Column(String, nullable=True)
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
app = FastAPI(title="نظام مياه الجعودية")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# Pydantic Schemas
class CustomerCreate(BaseModel):
    full_name: str
    phone: str
class MeterCreate(BaseModel):
    serial_number: str
    customer_id: int
    last_reading: int = 0
class ReadingInput(BaseModel):
    meter_id: int
    current_reading: int
    note: Optional[str] = None
class PaymentInput(BaseModel):
    customer_id: int
    amount: float

@app.get("/")
async def read_index():
    return FileResponse('index.html')

# ====================================================
# 4. العمليات (APIs)
# ====================================================

@app.post("/customers/")
def create_customer(item: CustomerCreate, db: Session = Depends(get_db)):
    if db.query(Customer).filter(Customer.phone == item.phone).first():
        raise HTTPException(status_code=400, detail="رقم الهاتف مسجل مسبقاً")
    new_customer = Customer(full_name=item.full_name, phone=item.phone)
    db.add(new_customer)
    db.commit()
    return new_customer

@app.post("/meters/")
def create_meter(item: MeterCreate, db: Session = Depends(get_db)):
    new_meter = Meter(serial_number=item.serial_number, customer_id=item.customer_id, last_reading=item.last_reading)
    db.add(new_meter)
    db.commit()
    return {"message": "تم تركيب العداد"}

# دالة إضافة القراءة مع منع النقرة المزدوجة والملاحظات
@app.post("/readings/")
def add_reading(item: ReadingInput, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == item.meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    
    if item.current_reading <= meter.last_reading:
        raise HTTPException(status_code=400, detail=f"خطأ: القراءة الحالية ({item.current_reading}) يجب أن تكون أكبر من السابقة ({meter.last_reading})")

    saved_previous_reading = meter.last_reading
    new_reading = Reading(
        meter_id=item.meter_id, 
        previous_reading=saved_previous_reading, 
        current_reading=item.current_reading,
        note=item.note
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    consumption = item.current_reading - saved_previous_reading
    price_setting = db.execute(text("SELECT value FROM system_settings WHERE key='unit_price'")).fetchone()
    unit_price = float(price_setting[0]) if price_setting else 100.0
    total_amount = consumption * unit_price

    new_invoice = Invoice(customer_id=meter.customer_id, reading_id=new_reading.id, amount=total_amount)
    db.add(new_invoice)
    
    customer = db.query(Customer).filter(Customer.id == meter.customer_id).first()
    customer.wallet_balance -= total_amount
    meter.last_reading = item.current_reading # تحديث حالة العداد
    
    db.commit()
    return {"message": "تم تسجيل القراءة بنجاح"}

@app.post("/payments/")
def make_payment(item: PaymentInput, db: Session = Depends(get_db)):
    new_payment = Payment(customer_id=item.customer_id, amount=item.amount)
    db.add(new_payment)
    customer = db.query(Customer).filter(Customer.id == item.customer_id).first()
    customer.wallet_balance += item.amount
    db.commit()
    return {"message": "تم السداد بنجاح"}

@app.get("/users_report/")
def get_users_report(db: Session = Depends(get_db)):
    sql = text("""
        SELECT 
            c.full_name, 
            m.serial_number, 
            COALESCE(r.previous_reading, 0) as prev_r, 
            COALESCE(r.current_reading, 0) as curr_r,
            COALESCE(r.current_reading - r.previous_reading, 0) as consumption,
            COALESCE(i.amount, 0) as last_amount,
            r.note,
            c.wallet_balance
        FROM customers c
        JOIN meters m ON c.id = m.customer_id
        LEFT JOIN (
            SELECT DISTINCT ON (meter_id) * FROM readings 
            ORDER BY meter_id, id DESC
        ) r ON r.meter_id = m.id
        LEFT JOIN invoices i ON i.reading_id = r.id
        ORDER BY c.id ASC
    """)
    return [dict(row) for row in db.execute(sql).mappings()]

@app.get("/dashboard/")
def get_dashboard(db: Session = Depends(get_db)):
    income = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM payments")).fetchone()[0]
    expenses = db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM expenses")).fetchone()[0]
    debts = db.execute(text("SELECT COALESCE(SUM(ABS(wallet_balance)), 0) FROM customers WHERE wallet_balance < 0")).fetchone()[0]
    return {"total_income": income, "total_expenses": expenses, "box_balance": income - expenses, "total_debts": debts}

@app.get("/customers/")
def get_customers(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.id).all()

@app.get("/meters/")
def get_meters(db: Session = Depends(get_db)):
    return db.query(Meter).order_by(Meter.id).all()

# دوال المصاريف
@app.post("/expenses/")
async def create_expense(title: str = Form(...), amount: float = Form(...), file: Optional[UploadFile] = File(None), db: Session = Depends(get_db)):
    image_path = None
    if file and file.filename:
        file_location = f"uploads/{file.filename}"
        with open(file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        image_path = file_location
    new_expense = Expense(title=title, amount=amount, image_path=image_path)
    db.add(new_expense)
    db.commit()
    return {"message": "تم الحفظ"}

@app.get("/expenses/")
def get_expenses(db: Session = Depends(get_db)):
    return db.query(Expense).order_by(Expense.expense_date.desc()).all()

