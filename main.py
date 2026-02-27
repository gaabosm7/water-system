# main.py
import os
import shutil
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# ====================================================
# 1. إعدادات قاعدة البيانات (متصلة بـ Supabase ☁️)
# ====================================================
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.lkefznnqjrktulahptfy:K4-!_jy#vkV+U9*@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"

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

# 💡 تم إضافة هذا الجدول لحل مشكلة الإعدادات وسعر الوحدة
class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True)
    value = Column(String)

# هذا السطر يقوم بإنشاء كل الجداول السابقة في Supabase فوراً
Base.metadata.create_all(bind=engine)

# ====================================================
# 3. التطبيق
# ====================================================
app = FastAPI(title="نظام مياه القرية")

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

# Pydantic Models
class CustomerCreate(BaseModel):
    full_name: str
    phone: str
class MeterCreate(BaseModel):
    serial_number: str
    customer_id: int
    last_reading: int = 0
class MeterUpdate(BaseModel):
    last_reading: int
class ReadingInput(BaseModel):
    meter_id: int
    current_reading: int
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

@app.put("/meters/{meter_id}")
def update_meter(meter_id: int, item: MeterUpdate, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    
    old_reading = meter.last_reading
    new_reading = item.last_reading
    diff_units = new_reading - old_reading
    
    price_setting = db.execute(text("SELECT value FROM system_settings WHERE key='unit_price'")).fetchone()
    unit_price = float(price_setting[0]) if price_setting else 100.0
    amount_diff = diff_units * unit_price
    
    meter.last_reading = new_reading
    
    customer = db.query(Customer).filter(Customer.id == meter.customer_id).first()
    customer.wallet_balance -= amount_diff
    
    db.commit()
    return {"message": "تم تعديل القراءة وتصحيح الرصيد"}

@app.delete("/meters/{meter_id}")
def delete_meter(meter_id: int, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    db.delete(meter)
    db.commit()
    return {"message": "تم حذف العداد"}

@app.put("/meters/{meter_id}/reset")
def reset_meter(meter_id: int, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    meter.last_reading = 0
    db.commit()
    return {"message": "تم تصفير العداد"}

@app.get("/customer_meter/{customer_id}")
def get_customer_meter(customer_id: int, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.customer_id == customer_id).first()
    if not meter: return {"status": "no_meter"}
    return {"status": "found", "meter_id": meter.id, "serial": meter.serial_number}

@app.post("/readings/")
def add_reading(item: ReadingInput, db: Session = Depends(get_db)):
    meter = db.query(Meter).filter(Meter.id == item.meter_id).first()
    if not meter: raise HTTPException(status_code=404, detail="العداد غير موجود")
    
    if item.current_reading < meter.last_reading:
        raise HTTPException(status_code=400, detail=f"خطأ: القراءة الحالية ({item.current_reading}) أقل من السابقة ({meter.last_reading})")

    saved_previous_reading = meter.last_reading
    new_reading = Reading(meter_id=item.meter_id, previous_reading=saved_previous_reading, current_reading=item.current_reading)
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    consumption = item.current_reading - saved_previous_reading
    price_setting = db.execute(text("SELECT value FROM system_settings WHERE key='unit_price'")).fetchone()
    unit_price = float(price_setting[0]) if price_setting else 100.0
    total_amount = consumption * unit_price

    new_invoice = Invoice(customer_id=meter.customer_id, reading_id=new_reading.id, amount=total_amount)
    db.add(new_invoice)
    db.commit()

    # 💡 تم إصلاح الخصم من الرصيد هنا
    customer = db.query(Customer).filter(Customer.id == meter.customer_id).first()
    customer.wallet_balance -= total_amount
    db.commit()
    db.refresh(customer)
    
    return {"message": "تمت العملية", "units": consumption, "cost": total_amount, "new_balance": customer.wallet_balance}

@app.post("/payments/")
def make_payment(item: PaymentInput, db: Session = Depends(get_db)):
    new_payment = Payment(customer_id=item.customer_id, amount=item.amount)
    db.add(new_payment)
    db.commit()
    
    # 💡 تم إصلاح الإضافة للرصيد هنا
    customer = db.query(Customer).filter(Customer.id == item.customer_id).first()
    customer.wallet_balance += item.amount
    db.commit()
    db.refresh(customer)
    
    return {"message": "تم السداد", "new_balance": customer.wallet_balance}

@app.post("/expenses/")
async def create_expense(
    title: str = Form(...),
    amount: float = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    image_path = None
    if file and file.filename:
        file_location = f"uploads/{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_path = file_location

    new_expense = Expense(title=title, amount=amount, image_path=image_path)
    db.add(new_expense)
    db.commit()
    return {"message": "تم حفظ المصروف"}

@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense: raise HTTPException(status_code=404, detail="المصروف غير موجود")
    if expense.image_path and os.path.exists(expense.image_path):
        try: os.remove(expense.image_path)
        except: pass
    db.delete(expense)
    db.commit()
    return {"message": "تم الحذف"}

@app.put("/expenses/{expense_id}")
async def update_expense(
    expense_id: int,
    title: str = Form(...),
    amount: float = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense: raise HTTPException(status_code=404, detail="المصروف غير موجود")
    
    expense.title = title
    expense.amount = amount

    if file and file.filename:
        if expense.image_path and os.path.exists(expense.image_path):
            try: os.remove(expense.image_path)
            except: pass  
        file_location = f"uploads/{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        expense.image_path = file_location

    db.commit()
    return {"message": "تم التعديل"}

@app.get("/expenses/")
def get_expenses(db: Session = Depends(get_db)):
    return db.query(Expense).order_by(Expense.expense_date.desc()).all()

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