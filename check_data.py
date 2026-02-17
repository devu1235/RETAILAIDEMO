import sqlite3

# Connect to database
conn = sqlite3.connect('instance/shop.db')
cursor = conn.cursor()

# Check all tables
print("="*50)
print("📊 DATABASE STATUS CHECK")
print("="*50)

# Check users
cursor.execute("SELECT COUNT(*) FROM user")
user_count = cursor.fetchone()[0]
print(f"👤 Users: {user_count}")
if user_count > 0:
    cursor.execute("SELECT id, username, shop_name FROM user")
    users = cursor.fetchall()
    for user in users:
        print(f"   - ID: {user[0]}, Username: {user[1]}, Shop: {user[2]}")

# Check products
cursor.execute("SELECT COUNT(*) FROM product")
product_count = cursor.fetchone()[0]
print(f"\n📦 Products: {product_count}")
if product_count > 0:
    cursor.execute("SELECT id, name, current_stock FROM product LIMIT 5")
    products = cursor.fetchall()
    for product in products:
        print(f"   - {product[1]}: {product[2]} units")

# Check stock_in
cursor.execute("SELECT COUNT(*) FROM stock_in")
stock_in_count = cursor.fetchone()[0]
print(f"\n📥 Stock In Records: {stock_in_count}")

# Check sales
cursor.execute("SELECT COUNT(*) FROM sale")
sale_count = cursor.fetchone()[0]
print(f"💰 Sales Records: {sale_count}")

if sale_count > 0:
    cursor.execute("SELECT SUM(total_amount) FROM sale")
    total_revenue = cursor.fetchone()[0] or 0
    print(f"   Total Revenue: ₹{total_revenue:,.2f}")
    
    cursor.execute("SELECT MIN(date), MAX(date) FROM sale")
    dates = cursor.fetchone()
    if dates[0]:
        print(f"   Date Range: {dates[0][:10]} to {dates[1][:10]}")

print("="*50)

conn.close()