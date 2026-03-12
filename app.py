from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func, extract
import calendar
import math
import numpy as np
import os
import smtplib
import base64
import urllib.parse
import urllib.request
from email.mime.text import MIMEText

def load_dotenv_file(path='.env'):
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # If .env cannot be read, app should continue with existing environment.
        pass

load_dotenv_file()

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

class LowStockAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    last_sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_known_stock = db.Column(db.Float, nullable=False, default=0)

# Create tables
with app.app_context():
    db.create_all()

LOW_STOCK_THRESHOLD = float(os.getenv('LOW_STOCK_THRESHOLD', '10'))
LOW_STOCK_COOLDOWN_HOURS = int(os.getenv('LOW_STOCK_COOLDOWN_HOURS', '24'))
LOW_STOCK_SMS_TO = os.getenv('LOW_STOCK_SMS_TO', '+917666150423')
LOW_STOCK_WHATSAPP_TO = os.getenv('LOW_STOCK_WHATSAPP_TO', 'whatsapp:+917666150423')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def _to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

def _send_email_alert(subject, body):
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    email_to = os.getenv('LOW_STOCK_EMAIL_TO')
    email_from = os.getenv('LOW_STOCK_EMAIL_FROM') or smtp_user
    use_tls = _to_bool(os.getenv('SMTP_USE_TLS', 'true'), True)

    if not smtp_host or not email_to or not email_from:
        return False

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = email_from
    msg['To'] = email_to

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(email_from, [email_to], msg.as_string())
        return True
    except Exception:
        return False

def _send_twilio_message(body, to_number, from_number):
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    if not sid or not token or not to_number or not from_number:
        return False

    endpoint = f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'
    payload = urllib.parse.urlencode({
        'To': to_number,
        'From': from_number,
        'Body': body
    }).encode('utf-8')
    auth = base64.b64encode(f'{sid}:{token}'.encode('utf-8')).decode('ascii')

    request = urllib.request.Request(endpoint, data=payload, method='POST')
    request.add_header('Authorization', f'Basic {auth}')
    request.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except Exception:
        return False

def _send_telegram_alert(body):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    endpoint = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = urllib.parse.urlencode({
        'chat_id': TELEGRAM_CHAT_ID,
        'text': body
    }).encode('utf-8')
    request = urllib.request.Request(endpoint, data=payload, method='POST')
    request.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except Exception:
        return False

def _clear_low_stock_alert_state(user_id, product_id):
    LowStockAlert.query.filter_by(user_id=user_id, product_id=product_id).delete()
    db.session.commit()

def maybe_send_low_stock_notification(product, user_id, trigger='stock_update'):
    if product is None:
        return

    if product.current_stock is None:
        return

    if product.current_stock >= LOW_STOCK_THRESHOLD:
        _clear_low_stock_alert_state(user_id, product.id)
        return

    now = datetime.utcnow()
    alert = LowStockAlert.query.filter_by(user_id=user_id, product_id=product.id).first()

    if alert and (now - alert.last_sent_at) < timedelta(hours=LOW_STOCK_COOLDOWN_HOURS):
        # Avoid alert spam when stock is unchanged during cooldown.
        if abs((alert.last_known_stock or 0) - product.current_stock) < 0.01:
            return

    subject = f'Low Stock Alert: {product.name}'
    body = (
        f'Low stock detected.\n'
        f'Product: {product.name}\n'
        f'Current stock: {product.current_stock} {product.unit or ""}\n'
        f'Threshold: {LOW_STOCK_THRESHOLD}\n'
        f'Trigger: {trigger}\n'
        f'Time (UTC): {now.strftime("%Y-%m-%d %H:%M:%S")}\n'
    )

    # Email
    _send_email_alert(subject, body)

    # SMS
    _send_twilio_message(
        body=body,
        to_number=LOW_STOCK_SMS_TO,
        from_number=os.getenv('TWILIO_SMS_FROM')
    )

    # WhatsApp (Twilio sandbox/number format usually starts with whatsapp:)
    _send_twilio_message(
        body=body,
        to_number=LOW_STOCK_WHATSAPP_TO,
        from_number=os.getenv('TWILIO_WHATSAPP_FROM')
    )

    # Telegram
    _send_telegram_alert(body)

    if not alert:
        alert = LowStockAlert(user_id=user_id, product_id=product.id)
        db.session.add(alert)

    alert.last_sent_at = now
    alert.last_known_stock = product.current_stock
    db.session.commit()

def send_manual_notification_test(user_id):
    user = User.query.get(user_id)
    title = "ShopEase Notification Test"
    body = (
        "This is a manual notification test from ShopEase.\n"
        f"User: {user.username if user else user_id}\n"
        f"Time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )

    sent_any = False
    sent_any = _send_email_alert(title, body) or sent_any
    sent_any = _send_twilio_message(
        body=body,
        to_number=LOW_STOCK_SMS_TO,
        from_number=os.getenv('TWILIO_SMS_FROM')
    ) or sent_any
    sent_any = _send_twilio_message(
        body=body,
        to_number=LOW_STOCK_WHATSAPP_TO,
        from_number=os.getenv('TWILIO_WHATSAPP_FROM')
    ) or sent_any
    sent_any = _send_telegram_alert(body) or sent_any
    return sent_any

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
    
    # Low stock products (less than threshold)
    low_stock_products = Product.query.filter(
        Product.user_id == user_id,
        Product.current_stock < LOW_STOCK_THRESHOLD
    ).all()
    low_stock = len(low_stock_products)

    # Trigger low-stock checks for existing items (cooldown-protected).
    for low_product in low_stock_products:
        maybe_send_low_stock_notification(low_product, user_id, trigger='dashboard_scan')
    
    inventory_value = db.session.query(
        func.sum(Product.current_stock * Product.cost_price)
    ).filter(
        Product.user_id == user_id
    ).scalar() or 0
    
    last_sale_ts = db.session.query(func.max(Sale.date)).filter(Sale.user_id == user_id).scalar()
    sales_30d = Sale.query.filter(
        Sale.user_id == user_id,
        Sale.date >= (datetime.now() - timedelta(days=30))
    ).count()
    active_days_30d = db.session.query(func.count(func.distinct(func.date(Sale.date)))).filter(
        Sale.user_id == user_id,
        Sale.date >= (datetime.now() - timedelta(days=30))
    ).scalar() or 0
    
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
                         inventory_value=inventory_value,
                         last_sale_ts=last_sale_ts,
                         sales_30d=sales_30d,
                         active_days_30d=active_days_30d,
                         recent_sales=recent_sales_data)

# ============= INVENTORY (SALES ENTRY) =============
@app.route('/inventory', methods=['GET', 'POST'])
def inventory():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        product_id = request.form['product_id']
        try:
            quantity = float(request.form['quantity'])
        except (TypeError, ValueError):
            return "Invalid quantity"
        
        if quantity <= 0:
            return "Quantity must be greater than 0"
        
        product = Product.query.filter_by(id=product_id, user_id=user_id).first()
        if not product:
            return "Invalid product selected"
        
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
            maybe_send_low_stock_notification(product, user_id, trigger='sale')
            
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
    
    today_total = sum(s["total"] for s in sales_with_names)
    today_items = sum(s["quantity"] for s in sales_with_names)
    
    return render_template('inventory.html', 
                         products=products,
                         sales=sales_with_names,
                         today_total=today_total,
                         today_items=today_items)

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
            try:
                selling_price = float(request.form['selling_price'])
                cost_price = float(request.form['cost_price'])
            except (TypeError, ValueError):
                return "Invalid price values"
            
            if not name.strip():
                return "Product name is required"
            if selling_price < 0 or cost_price < 0:
                return "Prices cannot be negative"
            
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
            try:
                quantity = float(request.form['quantity'])
                cost_price = float(request.form['cost_price'])
            except (TypeError, ValueError):
                return "Invalid quantity or cost price"
            
            if quantity <= 0:
                return "Quantity must be greater than 0"
            if cost_price < 0:
                return "Cost price cannot be negative"
            
            product = Product.query.filter_by(id=product_id, user_id=user_id).first()
            if not product:
                return "Invalid product selected"
            product.current_stock += quantity
            
            stock_entry = StockIn(
                product_id=product_id,
                quantity=quantity,
                cost_price=cost_price,
                user_id=user_id
            )
            db.session.add(stock_entry)
            db.session.commit()
            maybe_send_low_stock_notification(product, user_id, trigger='stock_in')
    
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
    
    low_stock_products = Product.query.filter(
        Product.user_id == user_id,
        Product.current_stock < LOW_STOCK_THRESHOLD
    ).all()
    stock_value = db.session.query(
        func.sum(Product.current_stock * Product.cost_price)
    ).filter(
        Product.user_id == user_id
    ).scalar() or 0
    
    return render_template('stock.html', 
                         products=products,
                         recent_stock=stock_with_names,
                         low_stock_products=low_stock_products,
                         stock_value=stock_value,
                         low_stock_threshold=LOW_STOCK_THRESHOLD,
                         notice=request.args.get('notice'))

@app.route('/notifications/test', methods=['POST'])
def notifications_test():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    sent_any = send_manual_notification_test(user_id)
    notice = (
        "Test notification sent. Check Telegram/SMS/Email channels."
        if sent_any
        else "No notification provider is configured. Please set Telegram/Email/SMS credentials."
    )
    return redirect(url_for('stock', notice=notice))

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
    last_7_label = "Real-time data"

    # Use current date by default, but if there are no sales in the current 7-day window,
    # fall back to the most recent day that has sales so analytics stays meaningful.
    anchor_date = now
    recent_7d_sales_count = Sale.query.filter(
        Sale.user_id == user_id,
        Sale.date >= (now - timedelta(days=6))
    ).count()

    if recent_7d_sales_count == 0:
        latest_sale = Sale.query.filter_by(user_id=user_id).order_by(Sale.date.desc()).first()
        if latest_sale:
            anchor_date = latest_sale.date
            last_7_label = f"Latest sales window (ending {anchor_date.strftime('%d %b %Y')})"

    for i in range(6, -1, -1):
        date = anchor_date - timedelta(days=i)
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
                         last_7_label=last_7_label,
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
            Sale.user_id == user_id,
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
                trend = 'Increasing'
                trend_factor = 1.2
            elif moving_avg < previous_avg * 0.9:
                trend = 'Decreasing'
                trend_factor = 0.8
            else:
                trend = 'Stable'
                trend_factor = 1.0
        else:
            moving_avg = sum(sales_values) / len(sales_values) if sales_values else 0
            trend = 'Limited data'
            trend_factor = 1.0
        
        # Calculate average daily sales
        avg_daily = moving_avg if moving_avg > 0 else 0
        
        # Seasonal adjustment (check if same month last year had higher sales)
        current_month = datetime.now().month
        last_year_sales = Sale.query.filter(
            Sale.product_id == product.id,
            Sale.user_id == user_id,
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

