from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)

    # NEW
    tribe_id = Column(Integer, nullable=True)              # Which tribe they selected
    tribal_id_number = Column(String(100), nullable=True)  # Optional ID
    is_verified = Column(Boolean, default=False, nullable=False)
    role = Column(String(30), default="member", nullable=False)  # 'member' | 'admin' | 'enrollment'
