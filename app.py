from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import List, Optional
from models import (
    init_db, get_db, SessionLocal, User, TravelPlan, Flight, Hotel, Day, DayItem,
    ShoppingItem, FixedExpense, OtherExpense
)
from auth import (
    get_password_hash, verify_password, create_access_token, get_current_user
)
import string
import random

app = FastAPI(title="Travel Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"init_db error: {e}")
    from sqlalchemy import text, inspect
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        columns = [c['name'] for c in inspector.get_columns('users')]
        if 'is_admin' not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            db.commit()
            print("Added is_admin column")
    except Exception as e:
        print(f"ALTER TABLE users error: {e}")
        db.rollback()
    try:
        first_user = db.query(User).order_by(User.id).first()
        if first_user and not first_user.is_admin:
            first_user.is_admin = True
            db.commit()
            print(f"Set {first_user.username} as admin")
    except Exception as e:
        print(f"Set admin error: {e}")
        db.rollback()
    db.close()
    print("Startup complete")


def generate_share_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ===== Pydantic Models =====
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PlanCreate(BaseModel):
    title: str = "旅行規劃"

class PlanUpdate(BaseModel):
    title: Optional[str] = None
    locked: Optional[bool] = None
    rate_krw: Optional[float] = None
    rate_jpy: Optional[float] = None
    rate_usd: Optional[float] = None
    people: Optional[List[str]] = None
    tips: Optional[dict] = None
    map_places: Optional[List[dict]] = None

class FlightData(BaseModel):
    id: Optional[int] = None
    fr: str = ""
    to: str = ""
    date: str = ""
    time: str = ""
    tag: str = ""
    price: int = 0
    order: int = 0

class HotelData(BaseModel):
    id: Optional[int] = None
    name: str = ""
    checkin: str = ""
    checkout: str = ""
    nights: int = 0
    price: int = 0
    order: int = 0

class DayItemData(BaseModel):
    id: Optional[int] = None
    time: str = ""
    title: str = ""
    note: str = ""
    metro: str = ""
    map_query: str = ""
    order: int = 0

class DayData(BaseModel):
    id: Optional[int] = None
    date: str = ""
    label: str = ""
    order: int = 0
    items: List[DayItemData] = []

class ShoppingData(BaseModel):
    id: Optional[int] = None
    name: str = ""
    store: str = ""
    kr: int = 0
    tw: int = 0
    bought: bool = False
    split_with: List[str] = []
    order: int = 0
    cur: str = "KRW"
    jpy: int = 0
    usd: float = 0
    photo: str = ""
    date: str = ""

class ExpenseData(BaseModel):
    id: Optional[int] = None
    name: str = ""
    note: str = ""
    cur: str = "TWD"
    amt: float = 0
    paid_by: str = ""
    split_with: List[str] = []
    order: int = 0


# ===== Auth Routes =====
@app.post("/api/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="帳號已存在")
    is_first = db.query(User).count() == 0
    user = User(username=req.username, password_hash=get_password_hash(req.password), is_admin=is_first)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)


@app.post("/api/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)


@app.get("/api/me")
def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/change-password")
def change_password(req: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="舊密碼錯誤")
    if len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="密碼至少4個字元")
    user.password_hash = get_password_hash(req.new_password)
    db.commit()
    return {"ok": True, "message": "密碼已更新"}


@app.post("/api/admin/force-admin")
def force_admin(req: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    user.is_admin = True
    db.commit()
    return {"ok": True, "message": f"{user.username} 已設為管理員"}


# ===== Admin Routes =====
@app.get("/api/admin/users")
def admin_list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理員權限")
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "is_admin": u.is_admin, "created_at": u.created_at.isoformat() if u.created_at else None, "plan_count": len(u.plans)} for u in users]


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理員權限")
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="不能刪除自己的帳號")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="找不到用戶")
    db.delete(target)
    db.commit()
    return {"ok": True, "message": f"已刪除 {target.username}"}


# ===== Plan Routes =====
def get_plan_with_access(plan_id: int, user: User, db: Session):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    if plan.user_id == user.id:
        return plan, "owner"
    shared = plan.shared_with or []
    for s in shared:
        if s.get("user_id") == user.id:
            return plan, s.get("permission", "readonly")
    raise HTTPException(status_code=403, detail="無權限存取此行程")


@app.get("/api/plans")
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned = db.query(TravelPlan).filter(TravelPlan.user_id == user.id).all()
    shared_ids = []
    for p in db.query(TravelPlan).filter(TravelPlan.shared_with != None).all():
        for s in (p.shared_with or []):
            if s.get("user_id") == user.id:
                shared_ids.append(p.id)
                break
    shared = db.query(TravelPlan).filter(TravelPlan.id.in_(shared_ids)).all() if shared_ids else []
    result = []
    for p in owned + shared:
        result.append({
            "id": p.id, "title": p.title,
            "updated_at": p.updated_at.isoformat(),
            "owner": p.user_id == user.id
        })
    return result


@app.post("/api/plans")
def create_plan(req: PlanCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = TravelPlan(user_id=user.id, title=req.title, share_code=generate_share_code())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "title": plan.title}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan, permission = get_plan_with_access(plan_id, user, db)
    result = serialize_plan(plan)
    result["permission"] = permission
    return result


@app.put("/api/plans/{plan_id}")
def update_plan(plan_id: int, req: PlanUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan, permission = get_plan_with_access(plan_id, user, db)
    if permission == "readonly":
        raise HTTPException(status_code=403, detail="唯讀權限，無法修改")
    for k, v in req.dict(exclude_unset=True).items():
        setattr(plan, k, v)
    db.commit()
    return {"ok": True}


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id, TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    db.delete(plan)
    db.commit()
    return {"ok": True}


class ShareRequest(BaseModel):
    username: str
    permission: str = "edit"  # "edit" or "readonly"

class ShareUpdate(BaseModel):
    permission: str


@app.get("/api/plans/{plan_id}/share-code")
def get_share_code(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id, TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    if not plan.share_code:
        plan.share_code = generate_share_code()
        db.commit()
    shared_users = []
    for s in (plan.shared_with or []):
        u = db.query(User).filter(User.id == s.get("user_id")).first()
        if u:
            shared_users.append({"id": u.id, "username": u.username, "permission": s.get("permission", "readonly")})
    return {"share_code": plan.share_code, "shared_with": shared_users}


@app.post("/api/plans/{plan_id}/share")
def share_plan(plan_id: int, req: ShareRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id, TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    target = db.query(User).filter(User.username == req.username).first()
    if not target:
        raise HTTPException(status_code=404, detail="找不到使用者：" + req.username)
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能共享給自己")
    shared = plan.shared_with or []
    for s in shared:
        if s.get("user_id") == target.id:
            raise HTTPException(status_code=400, detail="已經共享過了")
    shared.append({"user_id": target.id, "permission": req.permission})
    plan.shared_with = shared
    db.commit()
    return {"ok": True, "shared_with": req.username}


@app.put("/api/plans/{plan_id}/share/{username}")
def update_share_permission(plan_id: int, username: str, req: ShareUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id, TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="找不到使用者")
    shared = plan.shared_with or []
    for s in shared:
        if s.get("user_id") == target.id:
            s["permission"] = req.permission
            plan.shared_with = shared
            db.commit()
            return {"ok": True}
    raise HTTPException(status_code=404, detail="未共享此用戶")


@app.delete("/api/plans/{plan_id}/share/{username}")
def unshare_plan(plan_id: int, username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id, TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="找不到使用者")
    shared = plan.shared_with or []
    new_shared = [s for s in shared if s.get("user_id") != target.id]
    if len(new_shared) == len(shared):
        raise HTTPException(status_code=404, detail="未共享此用戶")
    plan.shared_with = new_shared
    db.commit()
    return {"ok": True}


@app.post("/api/plans/join/{share_code}")
def join_plan(share_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(TravelPlan).filter(TravelPlan.share_code == share_code).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到此分享碼對應的行程")
    if plan.user_id == user.id:
        return {"ok": True, "plan_id": plan.id, "message": "這是你自己的行程"}
    shared = plan.shared_with or []
    if user.id in shared:
        return {"ok": True, "plan_id": plan.id, "message": "你已經有存取權限"}
    shared.append(user.id)
    plan.shared_with = shared
    db.commit()
    return {"ok": True, "plan_id": plan.id, "message": "已成功加入共享"}


# ===== Sub-item Routes =====
@app.put("/api/plans/{plan_id}/flights")
def update_flights(plan_id: int, items: List[FlightData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    db.query(Flight).filter(Flight.plan_id == plan_id).delete()
    for i, item in enumerate(items):
        db.add(Flight(plan_id=plan_id, fr=item.fr, to=item.to, date=item.date, time=item.time, tag=item.tag, price=item.price, order=i))
    db.commit()
    return {"ok": True}


@app.put("/api/plans/{plan_id}/hotels")
def update_hotels(plan_id: int, items: List[HotelData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    db.query(Hotel).filter(Hotel.plan_id == plan_id).delete()
    for i, item in enumerate(items):
        db.add(Hotel(plan_id=plan_id, name=item.name, checkin=item.checkin, checkout=item.checkout, nights=item.nights, price=item.price, order=i))
    db.commit()
    return {"ok": True}


@app.put("/api/plans/{plan_id}/days")
def update_days(plan_id: int, items: List[DayData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    old_days = db.query(Day).filter(Day.plan_id == plan_id).all()
    for d in old_days:
        db.query(DayItem).filter(DayItem.day_id == d.id).delete()
        db.delete(d)
    db.flush()
    for i, day in enumerate(items):
        d = Day(plan_id=plan_id, date=day.date, label=day.label, order=i)
        db.add(d)
        db.flush()
        for j, item in enumerate(day.items):
            db.add(DayItem(day_id=d.id, time=item.time, title=item.title, note=item.note, metro=item.metro, map_query=item.map_query, order=j))
    db.commit()
    return {"ok": True}


@app.put("/api/plans/{plan_id}/shopping")
def update_shopping(plan_id: int, items: List[ShoppingData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    db.query(ShoppingItem).filter(ShoppingItem.plan_id == plan_id).delete()
    for i, item in enumerate(items):
        db.add(ShoppingItem(plan_id=plan_id, name=item.name, store=item.store, kr=item.kr, tw=item.tw, bought=item.bought, split_with=item.split_with, order=i))
    db.commit()
    return {"ok": True}


@app.put("/api/plans/{plan_id}/fixed")
def update_fixed(plan_id: int, items: List[ExpenseData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    db.query(FixedExpense).filter(FixedExpense.plan_id == plan_id).delete()
    for i, item in enumerate(items):
        db.add(FixedExpense(plan_id=plan_id, name=item.name, note=item.note, cur=item.cur, amt=item.amt, paid_by=item.paid_by, split_with=item.split_with, order=i))
    db.commit()
    return {"ok": True}


@app.put("/api/plans/{plan_id}/other")
def update_other(plan_id: int, items: List[ExpenseData], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_user_plan(plan_id, user.id, db)
    db.query(OtherExpense).filter(OtherExpense.plan_id == plan_id).delete()
    for i, item in enumerate(items):
        db.add(OtherExpense(plan_id=plan_id, name=item.name, note=item.note, cur=item.cur, amt=item.amt, paid_by=item.paid_by, split_with=item.split_with, order=i))
    db.commit()
    return {"ok": True}


# ===== Helpers =====
def get_user_plan(plan_id: int, user_id: int, db: Session) -> TravelPlan:
    plan = db.query(TravelPlan).filter(TravelPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到行程")
    shared = plan.shared_with or []
    if plan.user_id != user_id and user_id not in shared:
        raise HTTPException(status_code=403, detail="無權限存取此行程")
    return plan


def serialize_plan(plan: TravelPlan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "locked": plan.locked,
        "rate_krw": plan.rate_krw,
        "rate_jpy": plan.rate_jpy,
        "rate_usd": plan.rate_usd,
        "people": plan.people or [],
        "tips": plan.tips or {},
        "map_places": plan.map_places or [],
        "share_code": plan.share_code,
        "owner_id": plan.user_id,
        "flights": [{"id": f.id, "fr": f.fr, "to": f.to, "date": f.date, "time": f.time, "tag": f.tag, "price": f.price} for f in sorted(plan.flights, key=lambda x: x.order)],
        "hotels": [{"id": h.id, "name": h.name, "checkin": h.checkin, "checkout": h.checkout, "nights": h.nights, "price": h.price} for h in sorted(plan.hotels, key=lambda x: x.order)],
        "days": [
            {
                "id": d.id, "date": d.date, "label": d.label,
                "items": [{"id": i.id, "time": i.time, "title": i.title, "note": i.note, "metro": i.metro, "map_query": i.map_query} for i in sorted(d.items, key=lambda x: x.order)]
            }
            for d in sorted(plan.days, key=lambda x: x.order)
        ],
        "shopping": [{"id": s.id, "name": s.name, "store": s.store, "kr": s.kr, "tw": s.tw, "bought": s.bought, "split_with": s.split_with or [], "cur": s.cur or "KRW", "jpy": s.jpy or 0, "usd": s.usd or 0, "photo": s.photo or "", "date": s.date or ""} for s in sorted(plan.shopping, key=lambda x: x.order)],
        "fixed": [{"id": f.id, "name": f.name, "note": f.note, "cur": f.cur, "amt": f.amt, "paid_by": f.paid_by, "split_with": f.split_with or []} for f in sorted(plan.fixed_expenses, key=lambda x: x.order)],
        "other": [{"id": o.id, "name": o.name, "note": o.note, "cur": o.cur, "amt": o.amt, "paid_by": o.paid_by, "split_with": o.split_with or []} for o in sorted(plan.other_expenses, key=lambda x: x.order)],
    }


# ===== Static Files =====
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/app")
def app_page():
    return RedirectResponse(url="/static/main.html")
