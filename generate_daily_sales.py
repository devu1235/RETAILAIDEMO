import random
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


class DailySalesGenerator:
    def __init__(self, seed=42, months_back=18):
        self.seed = seed
        self.months_back = months_back
        random.seed(seed)
        np.random.seed(seed)

        self.conn = None
        self.cursor = None
        self.user_id = 1

        # id, name, category, unit, selling_price, cost_price, avg_daily
        self.products = [
            [1, "Lux Soap", "Personal Care", "piece", 45, 34, 11],
            [2, "Dove Soap", "Personal Care", "piece", 65, 50, 7],
            [3, "Lifebuoy Soap", "Personal Care", "piece", 35, 26, 13],
            [4, "Dove Shampoo", "Personal Care", "ml", 180, 138, 4],
            [5, "Clinic Plus", "Personal Care", "ml", 120, 90, 6],
            [6, "Colgate", "Personal Care", "grams", 85, 62, 8],
            [7, "Pepsodent", "Personal Care", "grams", 75, 55, 7],
            [8, "Amul Butter", "Dairy", "grams", 55, 41, 13],
            [9, "Amul Cheese", "Dairy", "grams", 120, 93, 6],
            [10, "Nestle Milk", "Dairy", "liter", 70, 54, 24],
            [11, "Amul Milk", "Dairy", "liter", 68, 53, 21],
            [12, "Curd", "Dairy", "kg", 50, 38, 11],
            [13, "Dairy Milk", "Snacks", "piece", 50, 36, 17],
            [14, "5 Star", "Snacks", "piece", 40, 30, 14],
            [15, "KitKat", "Snacks", "piece", 60, 45, 11],
            [16, "Lays Chips", "Snacks", "piece", 20, 13, 30],
            [17, "Kurkure", "Snacks", "piece", 20, 13, 27],
            [18, "Maggi", "Snacks", "piece", 14, 9, 25],
            [19, "Parle-G", "Snacks", "piece", 10, 6, 42],
            [20, "Tata Salt", "Grocery", "kg", 25, 17, 15],
            [21, "Aashirvaad Atta", "Grocery", "kg", 55, 43, 13],
            [22, "Fortune Oil", "Grocery", "liter", 120, 98, 8],
            [23, "Sugar", "Grocery", "kg", 45, 35, 10],
            [24, "Red Label Tea", "Grocery", "grams", 240, 190, 6],
            [25, "Surf Excel", "Household", "kg", 280, 220, 4],
            [26, "Vim Bar", "Household", "piece", 15, 9, 22],
            [27, "Harpic", "Household", "ml", 120, 87, 5],
            [28, "Coca Cola", "Beverages", "ml", 40, 28, 14],
            [29, "Pepsi", "Beverages", "ml", 40, 28, 14],
            [30, "Bisleri", "Beverages", "liter", 20, 12, 25],
        ]

    def setup_database(self):
        self.conn = sqlite3.connect("instance/shop.db")
        self.cursor = self.conn.cursor()

        self.cursor.execute("DELETE FROM sale")
        self.cursor.execute("DELETE FROM stock_in")
        self.cursor.execute("DELETE FROM product")
        self.cursor.execute("DELETE FROM user")

        self.cursor.execute(
            """
            INSERT INTO user (id, username, password, shop_name)
            VALUES (?, ?, ?, ?)
            """,
            (1, "demo_shop", "password123", "ShopEase Retail - Live Demo"),
        )

        for p in self.products:
            opening_stock = int(max(100, p[6] * random.randint(22, 35)))
            self.cursor.execute(
                """
                INSERT INTO product (id, name, category, unit, selling_price, cost_price, current_stock, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (p[0], p[1], p[2], p[3], p[4], p[5], opening_stock, self.user_id),
            )

        self.conn.commit()
        print("Database initialized")

    def month_factor(self, month, category):
        base = {
            1: 0.94,
            2: 0.92,
            3: 0.96,
            4: 1.02,
            5: 1.06,
            6: 1.01,
            7: 0.98,
            8: 1.04,
            9: 1.10,
            10: 1.22,
            11: 1.34,
            12: 1.16,
        }.get(month, 1.0)

        if category == "Beverages" and month in (4, 5, 6):
            base *= 1.25
        if category == "Dairy" and month in (4, 5):
            base *= 0.95
        return base

    def weekday_factor(self, weekday):
        # Mon=0 ... Sun=6
        return {0: 0.88, 1: 0.92, 2: 0.97, 3: 1.02, 4: 1.16, 5: 1.34, 6: 1.22}.get(weekday, 1.0)

    def event_factor(self, d):
        # A few recurring spikes to mimic local demand surges
        fixed_events = {(1, 1), (1, 26), (8, 15), (10, 2), (12, 25), (12, 31)}
        if (d.month, d.day) in fixed_events:
            return 1.35
        # Peak festive window around late Oct/Nov
        if d.month in (10, 11) and d.day in range(20, 31):
            return 1.25
        return 1.0

    def split_transactions(self, qty):
        if qty <= 1:
            return [qty]
        tx_count = min(qty, random.randint(1, 4))
        parts = [1] * tx_count
        remaining = qty - tx_count
        while remaining > 0:
            i = random.randint(0, tx_count - 1)
            parts[i] += 1
            remaining -= 1
        return parts

    def generate_data(self):
        start_date = (datetime.now() - timedelta(days=30 * self.months_back)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        sales_rows = []
        stock_rows = []
        sale_id = 1
        stock_id = 1

        stock_levels = {}
        product_map = {}

        self.cursor.execute(
            "SELECT id, name, category, unit, selling_price, cost_price, current_stock FROM product WHERE user_id = ?",
            (self.user_id,),
        )
        for row in self.cursor.fetchall():
            pid = row[0]
            stock_levels[pid] = float(row[6] or 0)
            product_map[pid] = {
                "name": row[1],
                "category": row[2],
                "unit": row[3],
                "selling": float(row[4]),
                "cost": float(row[5]),
                "base_daily": next(p[6] for p in self.products if p[0] == pid),
            }

        day_index = 0
        d = start_date

        while d <= end_date:
            weekday_mult = self.weekday_factor(d.weekday())
            event_mult = self.event_factor(d)

            # periodic replenishment days
            is_planned_restock_day = d.weekday() in (0, 3)

            for pid, info in product_map.items():
                month_mult = self.month_factor(d.month, info["category"])
                trend_mult = 1.0 + min(0.18, day_index / 4000.0)  # gentle growth over history
                noise = np.random.lognormal(mean=0.0, sigma=0.18)

                expected = info["base_daily"] * month_mult * weekday_mult * event_mult * trend_mult * noise

                if info["category"] == "Household":
                    expected *= 0.9
                if info["category"] == "Snacks" and d.weekday() >= 5:
                    expected *= 1.12

                demand_qty = int(np.random.poisson(max(expected, 0.05)))
                available = int(stock_levels[pid])
                sold_qty = min(demand_qty, max(available, 0))

                if sold_qty > 0:
                    for tx_qty in self.split_transactions(sold_qty):
                        hour = random.choices(
                            [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
                            weights=[2, 3, 4, 5, 6, 5, 5, 5, 6, 7, 10, 9, 6, 3],
                        )[0]
                        minute = random.randint(0, 59)
                        second = random.randint(0, 59)
                        ts = d.replace(hour=hour, minute=minute, second=second)

                        total = round(tx_qty * info["selling"], 2)
                        sales_rows.append(
                            (
                                sale_id,
                                pid,
                                float(tx_qty),
                                float(info["selling"]),
                                total,
                                ts.strftime("%Y-%m-%d %H:%M:%S"),
                                self.user_id,
                            )
                        )
                        sale_id += 1

                    stock_levels[pid] -= sold_qty

                # restock logic
                reorder_point = info["base_daily"] * 7
                if stock_levels[pid] < reorder_point and (is_planned_restock_day or random.random() < 0.28):
                    restock_qty = int(info["base_daily"] * random.randint(16, 32))
                    restock_cost = round(info["cost"] * random.uniform(0.96, 1.04), 2)
                    restock_time = d.replace(hour=7, minute=random.randint(10, 55), second=random.randint(0, 59))
                    stock_rows.append(
                        (
                            stock_id,
                            pid,
                            float(restock_qty),
                            restock_cost,
                            restock_time.strftime("%Y-%m-%d %H:%M:%S"),
                            self.user_id,
                        )
                    )
                    stock_id += 1
                    stock_levels[pid] += restock_qty

            if day_index % 30 == 0:
                print(f"Processed {d.strftime('%Y-%m-%d')} | sales rows so far: {len(sales_rows)}")

            d += timedelta(days=1)
            day_index += 1

        self.cursor.executemany(
            """
            INSERT INTO sale (id, product_id, quantity, selling_price, total_amount, date, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            sales_rows,
        )

        self.cursor.executemany(
            """
            INSERT INTO stock_in (id, product_id, quantity, cost_price, date, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            stock_rows,
        )

        for pid, qty in stock_levels.items():
            self.cursor.execute("UPDATE product SET current_stock = ? WHERE id = ?", (round(max(qty, 0), 2), pid))

        self.conn.commit()
        print(f"Generated {len(sales_rows)} sales rows and {len(stock_rows)} stock-in rows")

    def generate_daily_summary(self):
        self.cursor.execute(
            """
            SELECT DATE(date) AS sale_date,
                   COUNT(*) AS transactions,
                   SUM(quantity) AS items_sold,
                   SUM(total_amount) AS revenue,
                   AVG(total_amount) AS avg_transaction
            FROM sale
            WHERE user_id = ?
            GROUP BY DATE(date)
            ORDER BY sale_date
            """,
            (self.user_id,),
        )

        rows = self.cursor.fetchall()
        df = pd.DataFrame(rows, columns=["Date", "Transactions", "Items_Sold", "Revenue", "Avg_Transaction"])

        profits = []
        for date in df["Date"]:
            self.cursor.execute(
                """
                SELECT s.quantity, p.selling_price, p.cost_price
                FROM sale s
                JOIN product p ON s.product_id = p.id
                WHERE DATE(s.date) = ? AND s.user_id = ?
                """,
                (date, self.user_id),
            )
            day_sales = self.cursor.fetchall()
            day_profit = sum(q * (sp - cp) for q, sp, cp in day_sales)
            profits.append(round(day_profit, 2))

        df["Profit"] = profits
        df["Profit_Margin"] = (df["Profit"] / df["Revenue"] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)
        df.to_csv("daily_sales_summary.csv", index=False)

        print("Saved daily_sales_summary.csv")
        return df

    def run(self):
        print("Starting realistic data generation...")
        self.setup_database()
        self.generate_data()
        df = self.generate_daily_summary()

        self.cursor.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM sale WHERE user_id = ?", (self.user_id,))
        count, min_date, max_date = self.cursor.fetchone()

        print("Done")
        print(f"Transactions: {count}")
        print(f"Date range: {min_date} -> {max_date}")
        print("Login -> username: demo_shop | password: password123")

        self.conn.close()
        return df


if __name__ == "__main__":
    DailySalesGenerator().run()
