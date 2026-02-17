def generate_sales(self):
    """Generate realistic sales data for last 6 months"""
    sales_records = []
    start_date = datetime(2025, 8, 1)
    end_date = datetime(2026, 1, 31)
    
    # Seasonal multipliers (festival season = higher sales)
    seasonal_multipliers = {
        8: 1.0,   # August - Normal
        9: 1.1,   # September - Onam, Ganesh Chaturthi
        10: 1.15, # October - Navratri, Durga Puja
        11: 1.3,  # November - Diwali (peak)
        12: 1.25, # December - Christmas, New Year
        1: 1.1    # January - Post-holiday
    }
    
    # Weekend effect (higher sales on weekends)
    weekend_multiplier = 1.4
    friday_multiplier = 1.2
    monday_multiplier = 0.9  # Slightly lower on Mondays
    
    sale_id = 1000
    current_date = start_date
    
    # First, get all products from database
    self.cursor.execute("SELECT id, name, category, selling_price, cost_price, current_stock FROM product WHERE user_id = ?", (self.user_id,))
    db_products = self.cursor.fetchall()
    
    # Create a dictionary for quick access
    product_dict = {}
    for prod in db_products:
        product_dict[prod[1]] = {
            'id': prod[0],
            'category': prod[2],
            'selling_price': prod[3],
            'cost_price': prod[4],
            'current_stock': prod[5]
        }
    
    # Also keep the original products list for daily_avg
    products_with_avg = []
    for product in self.products:
        if product["name"] in product_dict:
            products_with_avg.append({
                'name': product["name"],
                'daily_avg': product["daily_avg"],
                'category': product["category"],
                'seasonal_factor': product["seasonal_factor"]
            })
    
    print(f"✅ Loaded {len(products_with_avg)} products for sales generation")
    
    while current_date <= end_date:
        month = current_date.month
        season_mult = seasonal_multipliers.get(month, 1.0)
        
        # Day of week multipliers
        weekday = current_date.weekday()  # 0=Monday, 6=Sunday
        if weekday >= 5:  # Weekend
            day_mult = weekend_multiplier
        elif weekday == 4:  # Friday
            day_mult = friday_multiplier
        elif weekday == 0:  # Monday
            day_mult = monday_multiplier
        else:
            day_mult = 1.0
        
        # Generate 15-30 transactions per day based on season
        base_transactions = random.randint(15, 25)
        num_transactions = int(base_transactions * season_mult * day_mult)
        
        for _ in range(num_transactions):
            # Pick a random product from products_with_avg
            product_info = random.choice(products_with_avg)
            product_name = product_info['name']
            db_product = product_dict.get(product_name)
            
            if not db_product:
                continue
                
            product_id = db_product['id']
            selling_price = db_product['selling_price']
            current_stock = db_product['current_stock']
            
            # Get daily average for this product
            daily_avg = product_info['daily_avg']
            category = product_info['category']
            seasonal_factor = product_info['seasonal_factor']
            
            # Determine quantity based on product type and day
            if category == "Grocery":
                # People buy more on weekends
                base_qty = random.randint(1, 3)
                qty_mult = 1.5 if weekday >= 5 else 1.0
                quantity = int(base_qty * qty_mult * season_mult * (daily_avg/5))
                
            elif category == "Dairy":
                # Daily essential - consistent
                quantity = random.randint(1, 2)
                if weekday >= 5:
                    quantity += 1
                quantity = int(quantity * (daily_avg/8))
                    
            elif category == "Snacks":
                # More snacks on weekends and evenings
                quantity = random.randint(1, 4)
                if weekday >= 5:
                    quantity = random.randint(2, 6)
                quantity = int(quantity * (daily_avg/15) * seasonal_factor)
                    
            elif category == "Beverages":
                # More cold drinks in summer (but we have winter data)
                quantity = random.randint(1, 3)
                if month in [8, 9, 10]:  # Slightly warmer months
                    quantity += 1
                quantity = int(quantity * (daily_avg/10))
                    
            else:  # Personal Care, Household
                quantity = 1
                if random.random() < 0.3:  # 30% chance of buying 2
                    quantity = 2
                quantity = int(quantity * (daily_avg/4))
            
            # Ensure minimum quantity is at least 1
            quantity = max(1, quantity)
            
            # Ensure we don't sell more than available
            if quantity > current_stock and current_stock > 0:
                quantity = max(1, int(current_stock * 0.5))
            elif current_stock <= 0:
                continue
            
            if quantity <= 0:
                continue
            
            # Calculate total
            total_amount = round(quantity * selling_price, 2)
            
            # Random time during business hours (weighted towards evening)
            hour_weights = [8,9,10,11,12,13,14,15,16,17,18,19,20,21]
            hour_probs = [0.03,0.04,0.06,0.08,0.10,0.08,0.07,0.07,0.08,0.09,0.11,0.09,0.06,0.04]
            hour = random.choices(hour_weights, weights=hour_probs)[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            
            sale_date = current_date.replace(hour=hour, minute=minute, second=second)
            
            sales_records.append((
                sale_id,
                product_id,
                quantity,
                selling_price,
                total_amount,
                sale_date.strftime("%Y-%m-%d %H:%M:%S"),
                self.user_id
            ))
            
            # Update current stock in our local dictionary
            db_product['current_stock'] -= quantity
            
            sale_id += 1
        
        # Commit every 7 days to avoid huge transactions
        if current_date.day % 7 == 0:
            # Update actual database stock periodically
            for product_name, prod_data in product_dict.items():
                self.cursor.execute('''
                    UPDATE product 
                    SET current_stock = ? 
                    WHERE id = ?
                ''', (prod_data['current_stock'], prod_data['id']))
            self.conn.commit()
            print(f"  Progress: Processed up to {current_date.strftime('%Y-%m-%d')}")
        
        current_date += timedelta(days=1)
    
    # Insert all sales records in batches to avoid memory issues
    batch_size = 500
    for i in range(0, len(sales_records), batch_size):
        batch = sales_records[i:i+batch_size]
        self.cursor.executemany('''
            INSERT INTO sale (id, product_id, quantity, selling_price, total_amount, date, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', batch)
        self.conn.commit()
        print(f"  Inserted sales batch {i//batch_size + 1}/{(len(sales_records)//batch_size)+1}")
    
    # Final stock update
    for product_name, prod_data in product_dict.items():
        self.cursor.execute('''
            UPDATE product 
            SET current_stock = ? 
            WHERE id = ?
        ''', (prod_data['current_stock'], prod_data['id']))
    self.conn.commit()
    
    print(f"✅ Generated {len(sales_records)} sales records")