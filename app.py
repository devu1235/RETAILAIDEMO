from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func, extract
import calendar
import math

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    shop_name = db.Column(db.String(200))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    current_stock = db.Column(db.Float, default=0)
    unit = db.Column(db.String(20))
    selling_price = db.Column(db.Float)
    cost_price = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class StockIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Float)
    cost_price = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    total_amount = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# Create tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        shop_name = request.form['shop_name']
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return "Username already exists! Try another."
        
        new_user = User(username=username, password=password, shop_name=shop_name)
        db.session.add(new_user)
        db.session.commit()
        
        return redirect('/login')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect('/dashboard')
        else:
            return "Invalid credentials! Try again."
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ============= DASHBOARD =============
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    # Today's sales
    today = datetime.now().date()
    today_sales = Sale.query.filter(
        func.date(Sale.date) == today,
        Sale.user_id == user_id
    ).all()
    
    total_today = sum(sale.total_amount for sale in today_sales)
    
    # This month's sales
    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_sales = Sale.query.filter(
        extract('month', Sale.date) == current_month,
        extract('year', Sale.date) == current_year,
        Sale.user_id == user_id
    ).all()
    
    total_month = sum(sale.total_amount for sale in monthly_sales)
    
    # Total products
    total_products = Product.query.filter_by(user_id=user_id).count()
    
    # Low stock products (less than 10 items)
    low_stock = Product.query.filter(
        Product.user_id == user_id,
        Product.current_stock < 10
    ).count()
    
    # Recent sales for table
    recent_sales = Sale.query.filter_by(user_id=user_id).order_by(Sale.date.desc()).limit(5).all()
    
    recent_sales_data = []
    for sale in recent_sales:
        product = Product.query.get(sale.product_id)
        recent_sales_data.append({
            'product_name': product.name if product else 'Unknown',
            'quantity': sale.quantity,
            'total': sale.total_amount,
            'time': sale.date.strftime('%H:%M')
        })
    
    return render_template('dashboard.html', 
                         username=session['username'],
                         total_today=total_today,
                         total_month=total_month,
                         total_products=total_products,
                         low_stock=low_stock,
                         recent_sales=recent_sales_data)

# ============= INVENTORY (SALES ENTRY) =============
@app.route('/inventory', methods=['GET', 'POST'])
def inventory():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        product_id = request.form['product_id']
        quantity = float(request.form['quantity'])
        
        product = Product.query.get(product_id)
        
        if product.current_stock >= quantity:
            total = quantity * product.selling_price
            
            sale = Sale(
                product_id=product_id,
                quantity=quantity,
                selling_price=product.selling_price,
                total_amount=total,
                user_id=user_id
            )
            
            product.current_stock -= quantity
            
            db.session.add(sale)
            db.session.commit()
            
            return redirect('/inventory')
        else:
            return f"Not enough stock! Available: {product.current_stock}"
    
    # Get all products for dropdown
    products = Product.query.filter_by(user_id=user_id).all()
    
    # Get today's sales
    today = datetime.now().date()
    today_sales = Sale.query.filter(
        func.date(Sale.date) == today,
        Sale.user_id == user_id
    ).order_by(Sale.date.desc()).all()
    
    sales_with_names = []
    for sale in today_sales:
        product = Product.query.get(sale.product_id)
        sales_with_names.append({
            'product_name': product.name if product else 'Unknown',
            'quantity': sale.quantity,
            'total': sale.total_amount,
            'time': sale.date.strftime('%H:%M')
        })
    
    return render_template('inventory.html', 
                         products=products,
                         sales=sales_with_names)

# ============= STOCK MANAGEMENT =============
@app.route('/stock', methods=['GET', 'POST'])
def stock():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        action = request.form['action']
        
        if action == 'add_product':
            name = request.form['name']
            category = request.form['category']
            unit = request.form['unit']
            selling_price = float(request.form['selling_price'])
            cost_price = float(request.form['cost_price'])
            
            new_product = Product(
                name=name,
                category=category,
                unit=unit,
                selling_price=selling_price,
                cost_price=cost_price,
                current_stock=0,
                user_id=user_id
            )
            db.session.add(new_product)
            db.session.commit()
            
        elif action == 'stock_in':
            product_id = request.form['product_id']
            quantity = float(request.form['quantity'])
            cost_price = float(request.form['cost_price'])
            
            product = Product.query.get(product_id)
            product.current_stock += quantity
            
            stock_entry = StockIn(
                product_id=product_id,
                quantity=quantity,
                cost_price=cost_price,
                user_id=user_id
            )
            db.session.add(stock_entry)
            db.session.commit()
    
    # Get all products
    products = Product.query.filter_by(user_id=user_id).all()
    
    # Get recent stock in entries
    recent_stock = StockIn.query.filter_by(user_id=user_id).order_by(StockIn.date.desc()).limit(10).all()
    
    stock_with_names = []
    for entry in recent_stock:
        product = Product.query.get(entry.product_id)
        stock_with_names.append({
            'product_name': product.name if product else 'Unknown',
            'quantity': entry.quantity,
            'date': entry.date.strftime('%Y-%m-%d %H:%M')
        })
    
    return render_template('stock.html', 
                         products=products,
                         recent_stock=stock_with_names)

@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    # Get current date info
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    current_month_name = calendar.month_name[current_month]
    today_date_formatted = now.strftime('%d %B %Y')
    
    # ===== TODAY'S SALES =====
    today = now.date()
    today_sales_data = Sale.query.filter(
        func.date(Sale.date) == today,
        Sale.user_id == user_id
    ).all()
    today_sales = sum(sale.total_amount for sale in today_sales_data) or 0
    
    # ===== THIS MONTH'S SALES =====
    monthly_sales_data = Sale.query.filter(
        extract('month', Sale.date) == current_month,
        extract('year', Sale.date) == current_year,
        Sale.user_id == user_id
    ).all()
    monthly_sales = sum(sale.total_amount for sale in monthly_sales_data) or 0
    
    # ===== AVERAGE DAILY SALES (LAST 30 DAYS) =====
    thirty_days_ago = now - timedelta(days=30)
    last_30_days_sales = Sale.query.filter(
        Sale.date >= thirty_days_ago,
        Sale.user_id == user_id
    ).all()
    
    if last_30_days_sales:
        avg_daily = sum(s.total_amount for s in last_30_days_sales) / 30
    else:
        avg_daily = 0
    
    # ===== BEST DAY EVER =====
    best_day_data = db.session.query(
        func.date(Sale.date).label('sale_date'),
        func.sum(Sale.total_amount).label('daily_total')
    ).filter(
        Sale.user_id == user_id
    ).group_by(
        func.date(Sale.date)
    ).order_by(
        func.sum(Sale.total_amount).desc()
    ).first()
    
    if best_day_data:
        best_day = best_day_data.daily_total
        # The date is already a string from func.date()
        best_day_date = best_day_data.sale_date  # Format: YYYY-MM-DD
    else:
        best_day = 0
        best_day_date = 'N/A'
    
    # ===== DAILY SALES FOR CHART (LAST 30 DAYS) =====
    daily_labels = []
    daily_data = []
    
    for i in range(29, -1, -1):
        date = now - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        day_sales = Sale.query.filter(
            func.date(Sale.date) == date_str,
            Sale.user_id == user_id
        ).all()
        daily_total = sum(s.total_amount for s in day_sales) or 0
        
        daily_labels.append(date.strftime('%d %b'))
        daily_data.append(daily_total)
    
    # ===== MONTHLY SALES FOR CHART =====
    monthly_labels = []
    monthly_data = []
    
    for i in range(5, -1, -1):
        month = current_month - i
        year = current_year
        if month <= 0:
            month += 12
            year -= 1
        
        month_sales = Sale.query.filter(
            extract('month', Sale.date) == month,
            extract('year', Sale.date) == year,
            Sale.user_id == user_id
        ).all()
        month_total = sum(s.total_amount for s in month_sales) or 0
        
        monthly_labels.append(calendar.month_abbr[month])
        monthly_data.append(month_total)
    
    # ===== WEEKDAY ANALYSIS =====
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekday_analysis = []
    
    weekday_totals = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    
    all_sales = Sale.query.filter_by(user_id=user_id).all()
    
    for sale in all_sales:
        weekday_num = sale.date.weekday()
        weekday_totals[weekday_num].append(sale.total_amount)
    
    max_avg_sales = 1  # Prevent division by zero in template
    for day_num in range(7):
        if weekday_totals[day_num]:
            avg_sales = sum(weekday_totals[day_num]) / len(weekday_totals[day_num])
            transactions = len(weekday_totals[day_num])
            max_avg_sales = max(max_avg_sales, avg_sales)
        else:
            avg_sales = 0
            transactions = 0
        
        weekday_analysis.append({
            'day': weekday_names[day_num],
            'avg_sales': avg_sales,
            'transactions': transactions
        })
    
    # ===== TOP PRODUCTS =====
    products = Product.query.filter_by(user_id=user_id).all()
    product_sales = []
    
    for product in products:
        sales = Sale.query.filter(
            Sale.product_id == product.id,
            Sale.user_id == user_id
        ).all()
        
        if sales:
            total_qty = sum(s.quantity for s in sales)
            total_revenue = sum(s.total_amount for s in sales)
            
            product_sales.append({
                'name': product.name,
                'quantity': total_qty,
                'revenue': total_revenue
            })
    
    top_products = sorted(product_sales, key=lambda x: x['revenue'], reverse=True)[:5]
    
    # ===== LAST 7 DAYS DETAILS =====
    last_7_days = []
    
    for i in range(6, -1, -1):
        date = now - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        
        day_sales = Sale.query.filter(
            func.date(Sale.date) == date_str,
            Sale.user_id == user_id
        ).all()
        
        if day_sales:
            transactions = len(day_sales)
            items = sum(s.quantity for s in day_sales)
            revenue = sum(s.total_amount for s in day_sales)
            
            profit = 0
            for sale in day_sales:
                product = Product.query.get(sale.product_id)
                if product:
                    profit += sale.quantity * (product.selling_price - product.cost_price)
            
            margin = round((profit / revenue * 100) if revenue > 0 else 0, 1)
        else:
            transactions = 0
            items = 0
            revenue = 0
            profit = 0
            margin = 0
        
        last_7_days.append({
            'date': date.strftime('%d %b'),
            'day_name': date.strftime('%A'),
            'transactions': transactions,
            'items': items,
            'revenue': revenue,
            'profit': profit,
            'margin': margin
        })
    
    # ===== CURRENT MONTH PROFIT =====
    current_month_profit = 0
    for sale in monthly_sales_data:
        product = Product.query.get(sale.product_id)
        if product:
            current_month_profit += sale.quantity * (product.selling_price - product.cost_price)
    
    profit_margin = round((current_month_profit / monthly_sales * 100) if monthly_sales > 0 else 0, 1)
    
    # ===== CATEGORY BREAKDOWN =====
    categories = {}
    for sale in monthly_sales_data:
        product = Product.query.get(sale.product_id)
        if product and product.category:
            if product.category not in categories:
                categories[product.category] = {
                    'sales': 0,
                    'revenue': 0
                }
            categories[product.category]['sales'] += sale.quantity
            categories[product.category]['revenue'] += sale.total_amount
    
    category_data = []
    max_category_revenue = 1  # Prevent division by zero
    for cat, data in categories.items():
        category_data.append({
            'category': cat,
            'sales': data['sales'],
            'revenue': data['revenue']
        })
        max_category_revenue = max(max_category_revenue, data['revenue'])
    
    # ===== MONTHS DATA FOR TABLE =====
    months_data = []
    for i in range(5, -1, -1):
        month = current_month - i
        year = current_year
        if month <= 0:
            month += 12
            year -= 1
        
        month_sales = Sale.query.filter(
            extract('month', Sale.date) == month,
            extract('year', Sale.date) == year,
            Sale.user_id == user_id
        ).all()
        
        month_total = sum(s.total_amount for s in month_sales) or 0
        
        month_profit = 0
        for sale in month_sales:
            product = Product.query.get(sale.product_id)
            if product:
                month_profit += sale.quantity * (product.selling_price - product.cost_price)
        
        months_data.append({
            'month': calendar.month_abbr[month],
            'sales': month_total,
            'profit': month_profit
        })
    
    # ===== ADDITIONAL METRICS =====
    unique_days = db.session.query(func.date(Sale.date)).distinct().filter(Sale.user_id == user_id).count()
    
    total_transactions = Sale.query.filter_by(user_id=user_id).count()
    avg_transaction = (monthly_sales / total_transactions) if total_transactions > 0 else 0
    
    ytd_sales = Sale.query.filter(
        extract('year', Sale.date) == current_year,
        Sale.user_id == user_id
    ).all()
    ytd_total = sum(s.total_amount for s in ytd_sales) or 0
    
    return render_template('analytics.html',
                         # Date info
                         now=now,
                         today_date_formatted=today_date_formatted,
                         
                         # Summary cards
                         today_sales=today_sales,
                         monthly_sales=monthly_sales,
                         avg_daily=avg_daily,
                         best_day=best_day,
                         best_day_date=best_day_date,
                         
                         # Additional metrics
                         ytd_sales=ytd_total,
                         avg_transaction=avg_transaction,
                         unique_days=unique_days,
                         
                         # Charts data
                         daily_labels=daily_labels,
                         daily_data=daily_data,
                         monthly_labels=monthly_labels,
                         monthly_data=monthly_data,
                         
                         # Analysis tables
                         weekday_analysis=weekday_analysis,
                         top_products=top_products,
                         last_7_days=last_7_days,
                         category_data=category_data,
                         months_data=months_data,
                         
                         # For template calculations
                         max_avg_sales=max_avg_sales,
                         max_category_revenue=max_category_revenue,
                         
                         # Current month details
                         current_month=current_month_name,
                         monthly_profit=current_month_profit,
                         profit_margin=profit_margin)
# ============= FIXED PREDICTION PAGE =============
@app.route('/prediction')
def prediction():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    products = Product.query.filter_by(user_id=user_id).all()
    
    predictions = []
    total_predicted_sales = 0
    total_recommended_stock = 0
    total_current_stock = 0
    
    # Get last 90 days sales for trend analysis
    ninety_days_ago = datetime.now() - timedelta(days=90)
    
    for product in products:
        # Get last 90 days sales
        sales_90d = Sale.query.filter(
            Sale.product_id == product.id,
            Sale.date >= ninety_days_ago
        ).order_by(Sale.date).all()
        
        if not sales_90d:
            # No sales data, use default prediction
            predictions.append({
                'product_name': product.name,
                'predicted_sales': 0,
                'recommended_stock': 0,
                'current_stock': product.current_stock,
                'confidence': 'Low',
                'trend': 'No data'
            })
            continue
        
        # Group sales by day for time series
        daily_sales = {}
        for sale in sales_90d:
            date_str = sale.date.strftime('%Y-%m-%d')
            if date_str not in daily_sales:
                daily_sales[date_str] = 0
            daily_sales[date_str] += sale.quantity
        
        # Calculate moving averages
        sales_values = list(daily_sales.values())
        if len(sales_values) > 7:
            # Calculate 7-day moving average for trend
            moving_avg = sum(sales_values[-7:]) / 7
            previous_avg = sum(sales_values[-14:-7]) / 7 if len(sales_values) > 14 else moving_avg
            
            # Determine trend
            if moving_avg > previous_avg * 1.1:
                trend = '📈 Increasing'
                trend_factor = 1.2
            elif moving_avg < previous_avg * 0.9:
                trend = '📉 Decreasing'
                trend_factor = 0.8
            else:
                trend = '➡️ Stable'
                trend_factor = 1.0
        else:
            moving_avg = sum(sales_values) / len(sales_values) if sales_values else 0
            trend = '📊 Limited data'
            trend_factor = 1.0
        
        # Calculate average daily sales
        avg_daily = moving_avg if moving_avg > 0 else 0
        
        # Seasonal adjustment (check if same month last year had higher sales)
        current_month = datetime.now().month
        last_year_sales = Sale.query.filter(
            Sale.product_id == product.id,
            extract('month', Sale.date) == current_month,
            extract('year', Sale.date) == (datetime.now().year - 1)
        ).all()
        
        seasonal_factor = 1.0
        if last_year_sales:
            last_year_avg = sum(s.quantity for s in last_year_sales) / 30  # Approximate daily
            if last_year_avg > avg_daily * 1.2:
                seasonal_factor = 1.3  # Strong seasonal demand
            elif last_year_avg > avg_daily:
                seasonal_factor = 1.1  # Slight seasonal demand
        
        # Calculate predicted monthly sales
        predicted_monthly = avg_daily * 30 * trend_factor * seasonal_factor
        
        # Recommended stock (with buffer based on sales variability)
        if sales_values:
            std_dev = np.std(sales_values) if len(sales_values) > 1 else avg_daily * 0.3
            cv = std_dev / avg_daily if avg_daily > 0 else 0.5  # Coefficient of variation
            
            # Higher buffer for variable products
            if cv > 0.5:
                buffer = 1.4  # 40% buffer for highly variable
            elif cv > 0.3:
                buffer = 1.2  # 20% buffer for moderately variable
            else:
                buffer = 1.1  # 10% buffer for stable products
        else:
            buffer = 1.2
        
        recommended = predicted_monthly * buffer
        
        # Determine confidence level
        if len(sales_values) > 60:
            confidence = 'High'
        elif len(sales_values) > 30:
            confidence = 'Medium'
        else:
            confidence = 'Low'
        
        predictions.append({
            'product_name': product.name,
            'predicted_sales': round(predicted_monthly, 1),
            'recommended_stock': round(recommended, 1),
            'current_stock': product.current_stock,
            'confidence': confidence,
            'trend': trend,
            'avg_daily': round(avg_daily, 1)
        })
        
        total_predicted_sales += predicted_monthly
        total_recommended_stock += recommended
        total_current_stock += product.current_stock
    
    # Sort predictions by recommended stock (highest first)
    predictions.sort(key=lambda x: x['recommended_stock'], reverse=True)
    
    # Get top 5 products that need restocking
    need_restock = [p for p in predictions if p['recommended_stock'] > p['current_stock']][:5]
    
    return render_template('prediction.html', 
                         predictions=predictions,
                         need_restock=need_restock,
                         total_predicted=round(total_predicted_sales, 1),
                         total_recommended=round(total_recommended_stock, 1),
                         total_current=round(total_current_stock, 1))

# Add numpy import for prediction
import numpy as np
    if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
