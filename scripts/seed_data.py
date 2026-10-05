import datetime
import os
import random
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faker import Faker

import app.models.models as models
from app.models.models import SessionLocal, create_tables


def seed_database(restaurant_id: int):
    create_tables()
    fake = Faker()
    session = SessionLocal()
    try:
        num_items = random.randint(5, 8)
        items = [
            f"{fake.unique.word().title()} {fake.word().title()}"
            for _ in range(num_items)
        ]

        start = datetime.date.today() - datetime.timedelta(days=13)
        for day_offset in range(14):
            day = start + datetime.timedelta(days=day_offset)
            for item in items:
                qty = random.randint(1, 50)
                unit_price = round(random.uniform(5.0, 100.0), 2)
                revenue = round(qty * unit_price, 2)
                session.add(
                    models.Sales(
                        restaurant_id=restaurant_id,
                        date=day,
                        item_name=item,
                        quantity_sold=qty,
                        revenue=revenue,
                    )
                )

        for item in items:
            session.add(
                models.Inventory(
                    restaurant_id=restaurant_id,
                    item_name=item,
                    quantity_in_stock=random.randint(0, 500),
                    cost_per_unit=round(random.uniform(2.0, 40.0), 2),
                )
            )

        for day_offset in range(14):
            day = start + datetime.timedelta(days=day_offset)
            hours = round(random.uniform(4.0, 12.0), 2)
            hourly = random.uniform(15.0, 35.0)
            session.add(
                models.Labor(
                    restaurant_id=restaurant_id,
                    date=day,
                    hours_worked=hours,
                    total_labor_cost=round(hours * hourly, 2),
                )
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database(1)
