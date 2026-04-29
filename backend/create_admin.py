import os, sys, hashlib, base64

ADMIN_USERNAME = "admin"
ADMIN_EMAIL    = "admin@example.com"
ADMIN_PASSWORD = "Admin1234!"
ADMIN_FULLNAME = "System Administrator"

os.environ.setdefault("DATABASE_URL", "postgresql://llm_user:llm_password@db:5432/llm_detector")
os.environ.setdefault("SECRET_KEY",   "dev-secret-key")
os.environ.setdefault("BOOTSTRAP_ADMIN_TOKEN", "dev")

import bcrypt as _bcrypt_lib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.database import User, UserRole

def make_hash(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    key    = base64.b64encode(digest)
    return _bcrypt_lib.hashpw(key, _bcrypt_lib.gensalt(12)).decode("utf-8")

engine  = create_engine(os.environ["DATABASE_URL"])
Session = sessionmaker(bind=engine)
db      = Session()

existing = db.query(User).filter(User.username == ADMIN_USERNAME).first()
if existing:
    print(f"[skip] user '{ADMIN_USERNAME}' already exists (id={existing.id})")
    sys.exit(0)

admin = User(
    email=ADMIN_EMAIL,
    username=ADMIN_USERNAME,
    full_name=ADMIN_FULLNAME,
    role=UserRole.ADMIN,
    hashed_password=make_hash(ADMIN_PASSWORD),
    is_active=True,
)
db.add(admin)
db.commit()
db.refresh(admin)
print(f"[ok] admin created — id={admin.id}")
print(f"     username = '{ADMIN_USERNAME}'")
print(f"     password = '{ADMIN_PASSWORD}'")
