import sqlite3
import random
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
import calendar
from collections import defaultdict

class DailySalesGenerator:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.user_id = 1
        
        # Product catalog with realistic daily sales patterns
        self.products = [
            # [id, name, category, unit, price, cost, avg_daily, seasonality]
            [1, "Lux Soap", "Personal Care", "piece", 45, 38, 12, 1.1],
            [2, "Dove Soap", "Personal Care", "piece", 65, 52, 8, 1.1],
            [3, "Lifebuoy Soap", "Personal Care", "piece", 35, 28, 15, 1.1],
            [4, "Dove Shampoo", "Personal Care", "ml", 180, 140, 5, 1.2],
            [5, "Clinic Plus", "Personal Care", "ml", 120, 95, 7, 1.2],
            [6, "Colgate", "Personal Care", "grams", 85, 70, 10, 1.1],
            [7, "Pepsodent", "Personal Care", "grams", 75, 60, 8, 1.1],
            [8, "Amul Butter", "Dairy", "grams", 55, 45, 15, 1.2],
            [9, "Amul Cheese", "Dairy", "grams", 120, 95, 8, 1.2],
            [10, "Nestle Milk", "Dairy", "liter", 70, 58, 25, 1.1],
            [11, "Amul Milk", "Dairy", "liter", 68, 55, 22, 1.1],
            [12, "Curd", "Dairy", "kg", 50, 40, 12, 1.2],
            [13, "Dairy Milk", "Snacks", "piece", 50, 40, 20, 1.4],
            [14, "5 Star", "Snacks", "piece", 40, 32, 15, 1.3],
            [15, "KitKat", "Snacks", "piece", 60, 48, 12, 1.3],
            [16, "Lays Chips", "Snacks", "piece", 20, 15, 35, 1.2],
            [17, "Kurkure", "Snacks", "piece", 20, 15, 30, 1.2],
            [18, "Maggi", "Snacks", "piece", 14, 10, 28, 1.2],
            [19, "Parle-G", "Snacks", "piece", 10, 7, 50, 1.1],
            [20, "Tata Salt", "Grocery", "kg", 25, 18, 18, 1.1],
            [21, "Aashirvaad Atta", "Grocery", "kg", 55, 45, 15, 1.2],
            [22, "Fortune Oil", "Grocery", "liter", 120, 100, 10, 1.2],
            [23, "Sugar", "Grocery", "kg", 45, 38, 12, 1.1],
            [24, "Red Label Tea", "Grocery", "grams", 240, 190, 8, 1.2],
            [25, "Surf Excel", "Household", "kg", 280, 230, 5, 1.1],
            [26, "Vim Bar", "Household", "piece", 15, 10, 25, 1.1],
            [27, "Harpic", "Household", "ml", 120, 90, 6, 1.1],
            [28, "Coca Cola", "Beverages", "ml", 40, 30, 18, 1.3],
            [29, "Pepsi", "Beverages", "ml", 40, 30, 18, 1.3],
            [30, "Bisleri", "Beverages", "liter", 20, 12, 30, 1.2],
        ]
        
    def setup_database(self):
        """Setup database connection and tables"""
        self.conn = sqlite3.connect('instance/shop.db')
        self.cursor = self.conn.cursor()
        
        # Clear existing data
        self.cursor.execute("DELETE FROM sale")
        self.cursor.execute("DELETE FROM stock_in")
        self.cursor.execute("DELETE FROM product")
        self.cursor.execute("DELETE FROM user")
        
        # Create demo user
        self.cursor.execute('''
            INSERT INTO user (id, username, password, shop_name)
            VALUES (?, ?, ?, ?)
        ''', (1, 'demo_shop', 'password123', 'Daily Sales Store'))
        
        # Insert products
        for p in self.products:
            self.cursor.execute('''
                INSERT INTO product (id, name, category, unit, selling_price, cost_price, current_stock, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (p[0], p[1], p[2], p[3], p[4], p[5], p[6] * 30, self.user_id))
        
        self.conn.commit()
        print("✅ Database setup complete")
    
    def generate_daily_sales(self):
        """Generate daily sales for last 6 months"""
        start_date = datetime(2025, 8, 1)
        end_date = datetime(2026, 1, 31)
        
        # Seasonal factors by month
        seasonal_factors = {
            8: 1.0,   # August - Normal
            9: 1.1,   # September - Festival start
            10: 1.15, # October - Navratri
            11: 1.4,  # November - Diwali (PEAK)
            12: 1.35, # December - Christmas
            1: 1.2    # January - New Year
        }
        
        # Weekend factors
        weekend_factors = {
            0: 0.9,   # Monday
            1: 0.95,  # Tuesday
            2: 1.0,   # Wednesday
            3: 1.0,   # Thursday
            4: 1.2,   # Friday
            5: 1.5,   # Saturday (PEAK)
            6: 1.4    # Sunday
        }
        
        # Special dates (festivals, holidays)
        special_dates = {
            "2025-10-02": 1.3,  # Gandhi Jayanti
            "2025-10-24": 2.0,  # Diwali (PEAK)
            "2025-11-01": 1.4,  # Karnataka Rajyotsava
            "2025-11-15": 1.3,  # Children's Day
            "2025-12-25": 2.0,  # Christmas (PEAK)
            "2025-12-31": 1.8,  # New Year Eve
            "2026-01-01": 1.5,  # New Year Day
            "2026-01-15": 1.3,  # Pongal/Makar Sankranti
            "2026-01-26": 1.2,  # Republic Day
        }
        
        daily_sales_data = []
        sale_id = 1000
        
        current_date = start_date
        print("\n📊 Generating daily sales...")
        
        while current_date <= end_date:
            month = current_date.month
            weekday = current_date.weekday()
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Base multiplier for the day
            day_multiplier = seasonal_factors.get(month, 1.0) * weekend_factors.get(weekday, 1.0)
            
            # Apply special date multiplier if applicable
            if date_str in special_dates:
                day_multiplier *= special_dates[date_str]
                print(f"   🎉 Special day {date_str}: {day_multiplier:.1f}x multiplier")
            
            # Number of transactions (20-50 per day based on multiplier)
            base_transactions = random.randint(25, 40)
            num_transactions = int(base_transactions * day_multiplier)
            
            # Track daily totals for summary
            daily_revenue = 0
            daily_profit = 0
            daily_items = 0
            
            for _ in range(num_transactions):
                # Pick random product
                product = random.choice(self.products)
                product_id = product[0]
                price = product[4]
                cost = product[5]
                avg_daily = product[6]
                
                # Quantity based on product type and day
                if product[2] == "Dairy":
                    # Essential - more consistent
                    quantity = random.randint(1, 3)
                    if weekday >= 5:  # Weekend
                        quantity += random.randint(1, 2)
                
                elif product[2] == "Grocery":
                    # Bulk purchases on weekends
                    quantity = random.randint(1, 2)
                    if weekday >= 5:
                        quantity = random.randint(2, 5)
                
                elif product[2] == "Snacks":
                    # More snacks on weekends and evenings
                    quantity = random.randint(1, 4)
                    if weekday >= 5:
                        quantity = random.randint(3, 8)
                    elif current_date.hour in [17, 18, 19, 20]:  # Evening hours
                        quantity += random.randint(1, 2)
                
                elif product[2] == "Beverages":
                    quantity = random.randint(1, 3)
                    if month in [8, 9]:  # Summer months
                        quantity += random.randint(1, 3)
                
                else:
                    quantity = random.randint(1, 2)
                
                # Apply day multiplier to quantity
                quantity = max(1, int(quantity * (day_multiplier ** 0.5)))
                
                # Calculate totals
                total = round(quantity * price, 2)
                profit = round(quantity * (price - cost), 2)
                
                # Random time during business hours (weighted towards evening)
                hour_weights = [8,9,10,11,12,13,14,15,16,17,18,19,20,21]
                hour_probs = [0.03,0.04,0.06,0.08,0.10,0.08,0.07,0.07,0.08,0.09,0.12,0.10,0.06,0.02]
                hour = random.choices(hour_weights, weights=hour_probs)[0]
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                
                sale_date = current_date.replace(hour=hour, minute=minute, second=second)
                
                daily_sales_data.append((
                    sale_id,
                    product_id,
                    quantity,
                    price,
                    total,
                    sale_date.strftime("%Y-%m-%d %H:%M:%S"),
                    self.user_id
                ))
                
                daily_revenue += total
                daily_profit += profit
                daily_items += quantity
                sale_id += 1
            
            # Print daily summary every 30 days
            if current_date.day == 1 or current_date.day == 15:
                print(f"   {date_str}: {num_transactions} transactions, ₹{daily_revenue:.0f} revenue, {daily_items} items")
            
            current_date += timedelta(days=1)
        
        # Insert in batches
        batch_size = 500
        for i in range(0, len(daily_sales_data), batch_size):
            batch = daily_sales_data[i:i+batch_size]
            self.cursor.executemany('''
                INSERT INTO sale (id, product_id, quantity, selling_price, total_amount, date, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', batch)
            self.conn.commit()
            print(f"   Inserted batch {i//batch_size + 1}/{(len(daily_sales_data)//batch_size)+1}")
        
        print(f"\n✅ Generated {len(daily_sales_data)} daily sales records")
        return daily_sales_data
    
    def generate_stock_in(self):
        """Generate stock in records"""
        stock_data = []
        stock_id = 1
        
        # Initial stock
        for product in self.products:
            product_id = product[0]
            quantity = product[6] * 60  # 2 months stock
            cost = product[5]
            
            stock_data.append((
                stock_id, product_id, quantity, cost,
                "2025-08-01 09:00:00", self.user_id
            ))
            stock_id += 1
        
        # Monthly restocking
        restock_dates = [
            "2025-09-01 10:00:00",
            "2025-10-01 10:00:00",
            "2025-11-01 10:00:00",
            "2025-12-01 10:00:00",
            "2026-01-01 10:00:00",
            "2026-01-15 10:00:00",  # Mid-month restock
        ]
        
        for date in restock_dates:
            for product in self.products:
                if random.random() < 0.7:  # 70% products restocked
                    product_id = product[0]
                    quantity = product[6] * 45  # 1.5 months stock
                    cost = product[5]
                    
                    stock_data.append((
                        stock_id, product_id, quantity, cost, date, self.user_id
                    ))
                    stock_id += 1
        
        self.cursor.executemany('''
            INSERT INTO stock_in (id, product_id, quantity, cost_price, date, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', stock_data)
        self.conn.commit()
        print(f"✅ Generated {len(stock_data)} stock in records")
        
        return stock_data
    
    def update_stock_levels(self):
        """Update current stock based on sales"""
        for product in self.products:
            product_id = product[0]
            
            # Total sold
            self.cursor.execute('''
                SELECT SUM(quantity) FROM sale WHERE product_id = ?
            ''', (product_id,))
            sold = self.cursor.fetchone()[0] or 0
            
            # Total received
            self.cursor.execute('''
                SELECT SUM(quantity) FROM stock_in WHERE product_id = ?
            ''', (product_id,))
            received = self.cursor.fetchone()[0] or 0
            
            current = received - sold
            self.cursor.execute('''
                UPDATE product SET current_stock = ? WHERE id = ?
            ''', (current, product_id))
        
        self.conn.commit()
        print("✅ Stock levels updated")
    
    def generate_daily_summary(self):
        """Generate a CSV with daily sales summary"""
        self.cursor.execute('''
            SELECT DATE(date) as sale_date, 
                   COUNT(*) as transactions,
                   SUM(quantity) as items_sold,
                   SUM(total_amount) as revenue,
                   AVG(total_amount) as avg_transaction
            FROM sale
            WHERE user_id = ?
            GROUP BY DATE(date)
            ORDER BY sale_date
        ''', (self.user_id,))
        
        daily_summary = self.cursor.fetchall()
        
        # Create DataFrame
        df = pd.DataFrame(daily_summary, 
                         columns=['Date', 'Transactions', 'Items_Sold', 'Revenue', 'Avg_Transaction'])
        
        # Add profit calculation
        profits = []
        for date in df['Date']:
            self.cursor.execute('''
                SELECT s.quantity, p.selling_price, p.cost_price
                FROM sale s
                JOIN product p ON s.product_id = p.id
                WHERE DATE(s.date) = ? AND s.user_id = ?
            ''', (date, self.user_id))
            
            day_sales = self.cursor.fetchall()
            day_profit = sum(q * (sp - cp) for q, sp, cp in day_sales)
            profits.append(day_profit)
        
        df['Profit'] = profits
        df['Profit_Margin'] = (df['Profit'] / df['Revenue'] * 100).round(1)
        
        # Save to CSV
        df.to_csv('daily_sales_summary.csv', index=False)
        print("✅ Daily summary saved to 'daily_sales_summary.csv'")
        
        return df
    
    def generate_analysis(self):
        """Generate analysis report"""
        print("\n" + "="*60)
        print("📊 DAILY SALES ANALYSIS (Last 6 Months)")
        print("="*60)
        
        # Overall statistics
        self.cursor.execute('''
            SELECT COUNT(*), SUM(total_amount), SUM(quantity), AVG(total_amount)
            FROM sale WHERE user_id = ?
        ''', (self.user_id,))
        total_trans, total_rev, total_items, avg_trans = self.cursor.fetchone()
        
        print(f"\n📈 OVERALL STATISTICS:")
        print(f"   Total Transactions: {total_trans}")
        print(f"   Total Revenue: ₹{total_rev:,.2f}")
        print(f"   Total Items Sold: {total_items:,.0f}")
        print(f"   Average Transaction: ₹{avg_trans:,.2f}")
        
        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN:")
        self.cursor.execute('''
            SELECT strftime('%Y-%m', date) as month,
                   COUNT(*) as transactions,
                   SUM(total_amount) as revenue,
                   SUM(quantity) as items
            FROM sale
            WHERE user_id = ?
            GROUP BY month
            ORDER BY month
        ''', (self.user_id,))
        
        monthly = self.cursor.fetchall()
        for month in monthly:
            print(f"   {month[0]}: {month[2]:>10.0f} revenue, {month[3]:>5.0f} items, {month[1]:>4} transactions")
        
        # Top products
        print(f"\n🏆 TOP 10 PRODUCTS:")
        self.cursor.execute('''
            SELECT p.name, COUNT(*) as times_sold, SUM(s.quantity) as total_qty, SUM(s.total_amount) as revenue
            FROM sale s
            JOIN product p ON s.product_id = p.id
            WHERE s.user_id = ?
            GROUP BY s.product_id
            ORDER BY revenue DESC
            LIMIT 10
        ''', (self.user_id,))
        
        top_products = self.cursor.fetchall()
        for i, prod in enumerate(top_products, 1):
            print(f"   {i}. {prod[0]}: {prod[3]:>8.0f} revenue, {prod[2]:>4} units")
        
        # Weekend vs Weekday
        print(f"\n📆 WEEKEND VS WEEKDAY:")
        self.cursor.execute('''
            SELECT 
                CASE WHEN cast(strftime('%w', date) as integer) IN (0,6) THEN 'Weekend' ELSE 'Weekday' END as day_type,
                COUNT(*) as transactions,
                AVG(total_amount) as avg_sale,
                SUM(total_amount) as total
            FROM sale
            WHERE user_id = ?
            GROUP BY day_type
        ''', (self.user_id,))
        
        day_types = self.cursor.fetchall()
        for dt in day_types:
            print(f"   {dt[0]}: {dt[3]:>8.0f} total, {dt[1]:>4} transactions, ₹{dt[2]:.0f} avg")
        
        print("="*60)
    
    def generate_predictions(self):
        """Generate next month predictions"""
        print("\n" + "="*60)
        print("🔮 NEXT MONTH PREDICTIONS")
        print("="*60)
        
        # Get last 3 months sales
        three_months_ago = datetime.now() - timedelta(days=90)
        
        predictions = []
        total_predicted_revenue = 0
        
        for product in self.products:
            product_id = product[0]
            product_name = product[1]
            price = product[4]
            
            # Get last 90 days sales
            self.cursor.execute('''
                SELECT DATE(date), SUM(quantity)
                FROM sale
                WHERE product_id = ? AND date >= ?
                GROUP BY DATE(date)
                ORDER BY date
            ''', (product_id, three_months_ago.strftime('%Y-%m-%d')))
            
            daily_sales = self.cursor.fetchall()
            
            if len(daily_sales) < 30:
                # Not enough data
                predicted = product[6] * 30  # Use average
            else:
                # Calculate trend
                quantities = [q[1] for q in daily_sales[-30:]]  # Last 30 days
                avg_daily = np.mean(quantities)
                
                # Check trend (compare first 15 days vs last 15 days)
                first_half = np.mean(quantities[:15]) if len(quantities) >= 15 else avg_daily
                second_half = np.mean(quantities[-15:]) if len(quantities) >= 15 else avg_daily
                
                if second_half > first_half * 1.1:
                    trend = "Increasing"
                    trend_factor = 1.15
                elif second_half < first_half * 0.9:
                    trend = "Decreasing"
                    trend_factor = 0.85
                else:
                    trend = "Stable"
                    trend_factor = 1.0
                
                # Seasonal adjustment
                next_month = datetime.now().month + 1
                if next_month > 12:
                    next_month = 1
                
                # November/December are high season
                if next_month in [11, 12]:
                    seasonal = 1.3
                elif next_month in [1, 10]:
                    seasonal = 1.15
                else:
                    seasonal = 1.0
                
                predicted = avg_daily * 30 * trend_factor * seasonal
            
            predicted_revenue = predicted * price
            total_predicted_revenue += predicted_revenue
            
            # Get current stock
            self.cursor.execute('''
                SELECT current_stock FROM product WHERE id = ?
            ''', (product_id,))
            current_stock = self.cursor.fetchone()[0] or 0
            
            predictions.append({
                'product': product_name,
                'predicted_units': round(predicted, 1),
                'predicted_revenue': round(predicted_revenue, 2),
                'current_stock': current_stock,
                'need_to_order': max(0, round(predicted * 1.2 - current_stock, 1))
            })
        
        # Sort by predicted revenue
        predictions.sort(key=lambda x: x['predicted_revenue'], reverse=True)
        
        print(f"\n📊 TOP 10 PRODUCTS BY PREDICTED REVENUE:")
        for i, p in enumerate(predictions[:10], 1):
            print(f"   {i}. {p['product']}:")
            print(f"      📈 Predicted: {p['predicted_units']} units (₹{p['predicted_revenue']:,.0f})")
            print(f"      📦 Current Stock: {p['current_stock']} units")
            if p['need_to_order'] > 0:
                print(f"      ⚠️ Need to order: {p['need_to_order']} units")
        
        print(f"\n💰 TOTAL PREDICTED REVENUE NEXT MONTH: ₹{total_predicted_revenue:,.0f}")
        print("="*60)
        
        return predictions
    
    def run(self):
        """Run the complete generator"""
        print("🚀 Starting Daily Sales Generator...")
        
        self.setup_database()
        self.generate_stock_in()
        self.generate_daily_sales()
        self.update_stock_levels()
        
        # Generate analysis and reports
        df = self.generate_daily_summary()
        self.generate_analysis()
        predictions = self.generate_predictions()
        
        self.conn.close()
        
        print("\n✅ Daily sales data generation complete!")
        print("\n📁 Files created:")
        print("   - instance/shop.db (SQLite database)")
        print("   - daily_sales_summary.csv (Daily sales summary)")
        
        print("\n🔐 Login credentials:")
        print("   Username: demo_shop")
        print("   Password: password123")
        
        return df, predictions

if __name__ == "__main__":
    generator = DailySalesGenerator()
    df, predictions = generator.run()
    
    # Show first few rows of daily summary
    print("\n📋 First 10 days of sales data:")
    print(df.head(10).to_string())