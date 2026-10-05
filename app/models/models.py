import os

from sqlalchemy import Column, Date, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Special characters in the password (e.g. "@") must be URL-encoded in DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it to a PostgreSQL connection URL (see .env.example)."
    )

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Sales(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, index=True)
    date = Column(Date, nullable=False)
    item_name = Column(String, nullable=False)
    quantity_sold = Column(Integer, nullable=False)
    revenue = Column(Float, nullable=False)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, index=True)
    item_name = Column(String, nullable=False)
    quantity_in_stock = Column(Integer, nullable=False)
    cost_per_unit = Column(Float, nullable=False)


class Labor(Base):
    __tablename__ = "labor"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, index=True)
    date = Column(Date, nullable=False)
    hours_worked = Column(Float, nullable=False)
    total_labor_cost = Column(Float, nullable=False)


def create_tables():
    Base.metadata.create_all(bind=engine)
