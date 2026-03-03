from flask import render_template, request, jsonify, redirect, url_for, flash
from sqlalchemy import select
from datetime import datetime, timedelta, date, timezone

from app import app, db
from app.models import User, Product, Order, OrderItem


# =====================================================================
# FONCTIONS UTILITAIRES
# =====================================================================

def get_daily_revenue_comparison():
    today = date.today()
    yesterday = today - timedelta(days=1)

    today_orders = db.session.query(Order).filter(
        db.func.date(Order.created_at) == today,
        Order.status.in_(["confirmed", "delivered"])
    ).all()
    today_revenue = sum(order.get_total_price() for order in today_orders)

    yesterday_orders = db.session.query(Order).filter(
        db.func.date(Order.created_at) == yesterday,
        Order.status.in_(["confirmed", "delivered"])
    ).all()
    yesterday_revenue = sum(order.get_total_price() for order in yesterday_orders)

    # Éviter la division par zéro si aucune donnée hier
    can_compare = yesterday_revenue > 0

    if can_compare:
        percentage_change = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
        is_increase = percentage_change >= 0
        sign = "+" if is_increase else ""
        display_value = f"{sign}{percentage_change:.1f}%"
    else:
        percentage_change = 0
        is_increase = True
        display_value = "N/A"

    return {
        'today_revenue': today_revenue,
        'yesterday_revenue': yesterday_revenue,
        'percentage_change': percentage_change,
        'is_increase': is_increase,
        'display_value': display_value,
        'can_compare': can_compare
    }


def get_monthly_orders_comparison():
    today = date.today()
    first_day_this_month = date(today.year, today.month, 1)

    if today.month == 1:
        first_day_last_month = date(today.year - 1, 12, 1)
        last_day_last_month = date(today.year, 1, 1) - timedelta(days=1)
    else:
        first_day_last_month = date(today.year, today.month - 1, 1)
        last_day_last_month = first_day_this_month - timedelta(days=1)

    this_month_orders = db.session.query(Order).filter(
        db.func.date(Order.created_at) >= first_day_this_month,
        db.func.date(Order.created_at) <= today
    ).count()

    last_month_orders = db.session.query(Order).filter(
        db.func.date(Order.created_at) >= first_day_last_month,
        db.func.date(Order.created_at) <= last_day_last_month
    ).count()

    can_compare = last_month_orders > 0

    if can_compare:
        percentage_change = ((this_month_orders - last_month_orders) / last_month_orders) * 100
        is_increase = percentage_change >= 0
        sign = "+" if is_increase else ""
        display_value = f"{sign}{percentage_change:.0f}%"
    else:
        percentage_change = 0
        is_increase = True
        display_value = "N/A"

    return {
        'this_month_count': this_month_orders,
        'last_month_count': last_month_orders,
        'percentage_change': percentage_change,
        'is_increase': is_increase,
        'display_value': display_value,
        'can_compare': can_compare
    }


def get_revenue_by_status():
    statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
    result = {s: 0.0 for s in statuses}

    orders = db.session.query(Order).all()
    for order in orders:
        if order.status in result:
            result[order.status] += order.get_total_price()
        else:
            result[order.status] = order.get_total_price()

    return result


def get_top_products():
    from sqlalchemy import func

    stmt = (
        db.session.query(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label('total_quantity'),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label('total_revenue')
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .group_by(Product.id, Product.name)
        .order_by(db.desc('total_quantity'))
        .limit(5)
    )

    results = stmt.all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "quantity": r.total_quantity,
            "revenue": float(r.total_revenue)
        }
        for r in results
    ]


def get_chart_data(days=7):
    today = datetime.now(timezone.utc)
    if not today.tzinfo:
        today = datetime.now()

    today_date = today.date()
    start_date = today_date - timedelta(days=days - 1)

    orders = db.session.query(Order).filter(
        db.func.date(Order.created_at) >= start_date,
        db.func.date(Order.created_at) <= today_date
    ).all()

    # Regroupement par date pour éviter les requêtes N+1
    orders_by_day = {}
    for order in orders:
        day_str = order.created_at.astimezone(timezone.utc).date() if order.created_at.tzinfo else order.created_at.date()
        day_str = day_str.strftime("%Y-%m-%d")
        orders_by_day.setdefault(day_str, []).append(order)

    labels, orders_count, revenue_data = [], [], []
    for i in range(days - 1, -1, -1):
        day = today_date - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        labels.append(day_str)
        day_orders = orders_by_day.get(day_str, [])
        orders_count.append(len(day_orders))
        revenue_data.append(sum(o.get_total_price() for o in day_orders))

    return {"labels": labels, "orders_count": orders_count, "revenue": revenue_data}


# =====================================================================
# PAGES HTML
# =====================================================================

@app.route("/")
def index():
    stmt = select(Order).order_by(Order.id.desc())
    all_orders = db.session.scalars(stmt).all()
    recent_orders = all_orders[:3] if all_orders else []

    stmt = select(Product).order_by(Product.id.asc())
    all_products = db.session.scalars(stmt).all()

    stmt = select(User).order_by(User.id.desc())
    all_users = db.session.scalars(stmt).all()

    confirmed_orders = [o for o in all_orders if o.status in ["confirmed", "delivered", "processing", "shipped"]]
    total_revenue = sum(o.get_total_price() for o in confirmed_orders)

    pending_confirmed_count = len([o for o in all_orders if o.status in ["pending", "confirmed"]])

    # Marge et valeur moyenne estimées (25 % de marge brute)
    profit = total_revenue * 0.25
    avg_order_value = (total_revenue / len(confirmed_orders)) if confirmed_orders else 0
    conversion_rate = 2.4  # valeur simulée, pas de tracking des visites

    return render_template(
        "index.html",
        orders=all_orders,
        recent_orders=recent_orders,
        products=all_products,
        users=all_users,
        total_revenue=total_revenue,
        chart_data=get_chart_data(days=7),
        revenue_by_status=get_revenue_by_status(),
        top_products=get_top_products(),
        pending_confirmed_count=pending_confirmed_count,
        revenue_comparison=get_daily_revenue_comparison(),
        orders_comparison=get_monthly_orders_comparison(),
        profit=profit,
        avg_order=avg_order_value,
        conversion_rate=conversion_rate,
    )


@app.route("/api/chart-data")
def api_chart_data():
    days = request.args.get("days", 7, type=int)
    if days not in [7, 30, 365]:
        return jsonify({"error": "days doit être 7, 30 ou 365"}), 400
    return jsonify(get_chart_data(days=days)), 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    return redirect(url_for("login"))


@app.route("/products")
def products():
    stmt = select(Product).order_by(Product.id.asc())
    all_products = db.session.scalars(stmt).all()
    return render_template("products.html", products=all_products)


@app.route("/users")
def users():
    stmt = select(User).order_by(User.id.desc())
    all_users = db.session.scalars(stmt).all()
    return render_template("users.html", users=all_users)


@app.route("/orders")
def orders():
    stmt = select(Order).order_by(Order.user_id.asc(), Order.id.asc())
    all_orders = db.session.scalars(stmt).all()

    orders_by_user = {}
    for order in all_orders:
        if order.user_id not in orders_by_user:
            orders_by_user[order.user_id] = {'user': order.user, 'orders': []}
        orders_by_user[order.user_id]['orders'].append(order)

    return render_template("orders.html", orders_by_user=orders_by_user)


@app.route("/broadcast")
def broadcast():
    return render_template("broadcast.html")


@app.route("/settings")
def settings():
    return render_template("settings.html")


# =====================================================================
# API — GESTION DES CLIENTS
# =====================================================================

@app.get("/api/users")
def get_users():
    stmt = select(User).order_by(User.id.desc())
    users = db.session.scalars(stmt).all()
    return jsonify([u.to_dict() for u in users])


@app.get("/api/users/<int:user_id>/orders")
def get_user_orders(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Client introuvable"}), 404

    stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    orders = db.session.scalars(stmt).all()

    status_labels = {
        "pending":    {"label": "En attente",    "color": "amber"},
        "confirmed":  {"label": "Confirmée",     "color": "blue"},
        "processing": {"label": "En traitement", "color": "indigo"},
        "shipped":    {"label": "Expédiée",      "color": "purple"},
        "delivered":  {"label": "Livrée",        "color": "green"},
        "cancelled":  {"label": "Annulée",       "color": "red"},
    }

    result = []
    for order in orders:
        s = status_labels.get(order.status, {"label": order.status, "color": "gray"})
        created = order.created_at
        if created.tzinfo:
            from datetime import timezone as tz
            created = created.astimezone(tz.utc)
        result.append({
            "id": order.id,
            "status": order.status,
            "status_label": s["label"],
            "status_color": s["color"],
            "date": created.strftime("%d/%m/%Y à %H:%M"),
            "total": float(order.get_total_price()),
            "items": [
                {
                    "name": item.product.name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "subtotal": float(item.quantity * item.unit_price)
                }
                for item in order.items
            ]
        })

    return jsonify({
        "user": {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "address": user.address
        },
        "total_orders": len(result),
        # On exclut les commandes annulées et en attente du total dépensé
        "total_spent": sum(o["total"] for o in result if o["status"] not in ["cancelled", "pending"]),
        "orders": result
    }), 200


@app.post("/api/users")
def create_user():
    data = request.get_json(silent=True) or {}

    required = ["name", "phone", "address"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Champs manquants : {', '.join(missing)}"}), 400

    stmt = select(User).where(User.phone == data["phone"])
    if db.session.scalar(stmt):
        return jsonify({"error": "Ce numéro de téléphone existe déjà"}), 409

    user = User(
        name=data["name"].strip(),
        phone=data["phone"].strip(),
        address=data["address"].strip(),
        email=data.get("email")
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


# =====================================================================
# API — GESTION DES PRODUITS
# =====================================================================

@app.get("/api/products")
def get_products():
    stmt = select(Product).where(Product.is_active.is_(True))
    products = db.session.scalars(stmt).all()
    return jsonify([
        {"id": p.id, "sku": p.sku, "name": p.name, "price": p.price}
        for p in products
    ])


@app.post("/api/products")
def create_product():
    data = request.get_json(silent=True) or {}

    required = ["sku", "name", "price"]
    missing = [k for k in required if data.get(k) in (None, "")]
    if missing:
        return jsonify({"error": f"Champs manquants : {', '.join(missing)}"}), 400

    if not isinstance(data["price"], (int, float)) or data["price"] <= 0:
        return jsonify({"error": "Le prix doit être un nombre positif"}), 400

    if db.session.scalar(select(Product).where(Product.sku == data["sku"])):
        return jsonify({"error": "Ce SKU existe déjà"}), 409

    stock = data.get("stock", 0)
    is_active = data.get("is_active", True)

    if not isinstance(stock, int) or stock < 0:
        stock = 0
    if not isinstance(is_active, bool):
        is_active = True

    product = Product(
        sku=data["sku"].strip(),
        name=data["name"].strip(),
        price=data["price"],
        stock=stock,
        is_active=is_active
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({
        "id": product.id, "sku": product.sku, "name": product.name,
        "price": product.price, "stock": product.stock, "is_active": product.is_active
    }), 201


@app.put("/api/products/<int:product_id>")
def update_product(product_id):
    data = request.get_json(silent=True) or {}

    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Produit introuvable"}), 404

    if data.get("name"):
        product.name = data["name"].strip()

    if data.get("price") is not None:
        price = data["price"]
        if not isinstance(price, (int, float)) or price <= 0:
            return jsonify({"error": "Le prix doit être positif"}), 400
        product.price = float(price)

    if data.get("stock") is not None:
        stock = data["stock"]
        if not isinstance(stock, int) or stock < 0:
            return jsonify({"error": "Le stock doit être un entier non négatif"}), 400
        product.stock = stock
        # stock est épuisé
        if product.stock == 0:
            product.is_active = False

    if "is_active" in data:
        product.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify({
        "id": product.id, "sku": product.sku, "name": product.name,
        "price": product.price, "stock": product.stock, "is_active": product.is_active
    }), 200


# =====================================================================
# API — GESTION DES COMMANDES
# =====================================================================

@app.get("/api/orders/<int:order_id>")
def get_order_details(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Commande introuvable"}), 404

    return jsonify({
        "id": order.id,
        "status": order.status,
        "user_id": order.user_id,
        "user": {
            "id": order.user.id,
            "name": order.user.name,
            "phone": order.user.phone,
            "address": order.user.address
        },
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product.name,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price)
            } for i in order.items
        ],
        "total_price": float(order.get_total_price())
    })


@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or {}

    user_data = data.get("user")
    items = data.get("items")

    if not user_data:
        return jsonify({"error": "Données client requises"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Articles requis"}), 400

    phone = user_data.get("phone")
    if not phone:
        return jsonify({"error": "Numéro de téléphone requis"}), 400

    # Validation complète des articles avant toute modification en base
    for item in items:
        product_id = item.get("product_id")
        if not isinstance(product_id, int):
            return jsonify({"error": "product_id invalide"}), 400
        quantity = item.get("quantity", 1)
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"error": "La quantité doit être un entier positif"}), 400
        product = db.session.get(Product, product_id)
        if not product or not product.is_active:
            return jsonify({"error": f"Produit {product_id} introuvable"}), 404

    for item in items:
        product = db.session.get(Product, item["product_id"])
        product.stock -= item.get("quantity", 1)
        if product.stock < 0:
            return jsonify({"error": f"Stock insuffisant pour le produit {product.id}"}), 400
        if product.stock == 0:
            product.is_active = False

    # Création ou récupération du client par numéro de téléphone
    user = db.session.scalar(select(User).where(User.phone == phone))
    if not user:
        user = User(
            name=user_data.get("name", "Inconnu").strip(),
            phone=phone.strip(),
            address=user_data.get("address", ""),
            email=user_data.get("email")
        )
        db.session.add(user)
        db.session.flush()

    order = Order(user_id=user.id, status="pending")
    db.session.add(order)
    db.session.flush()

    for item in items:
        product = db.session.get(Product, item["product_id"])
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item.get("quantity", 1),
            unit_price=product.price
        ))

    db.session.commit()
    return jsonify(order.to_dict()), 201


@app.route("/update-order-status", methods=["POST"])
def update_order_status():
    data = request.json
    if not data:
        return jsonify({"error": "Aucune donnée fournie"}), 400

    order_id = data.get("order_id")
    new_status = data.get("status")

    if not order_id:
        return jsonify({"error": "order_id requis"}), 400
    if not new_status:
        return jsonify({"error": "status requis"}), 400

    valid_statuses = ["pending", "confirmed", "cancelled", "processing", "shipped", "delivered"]
    if new_status not in valid_statuses:
        return jsonify({"error": f"Statut invalide. Valeurs acceptées : {', '.join(valid_statuses)}"}), 400

    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Commande introuvable"}), 404

    old_status = order.status
    order.status = new_status
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Statut mis à jour : '{old_status}' → '{new_status}'",
        "order_id": order.id,
        "status": order.status
    }), 200


# =====================================================================
# API — NOTIFICATIONS
# =====================================================================

@app.get("/api/notifications")
def get_notifications():
    notifications = []
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # Nouvelles commandes en attente (dernières 24 h)
    new_orders = db.session.query(Order).filter(
        Order.status == "pending",
        Order.created_at >= cutoff_24h
    ).order_by(Order.created_at.desc()).limit(10).all()

    for order in new_orders:
        total = order.get_total_price()
        age_minutes = int((now - order.created_at.astimezone(timezone.utc)).total_seconds() / 60)
        if age_minutes < 60:
            time_label = f"il y a {age_minutes} min"
        elif age_minutes < 1440:
            time_label = f"il y a {age_minutes // 60}h"
        else:
            time_label = f"il y a {age_minutes // 1440}j"

        notifications.append({
            "id": f"order_{order.id}",
            "type": "new_order",
            "color": "blue",
            "icon": "🛒",
            "title": f"Nouvelle commande #{order.id}",
            "message": f"{order.user.name} • {total:.0f} DH",
            "time": time_label,
            "link": "/orders",
            "read": False
        })

    # Produits avec stock faible ou épuisé (≤ 5 unités)
    low_stock = db.session.query(Product).filter(
        Product.stock <= 5,
        Product.is_active == True
    ).order_by(Product.stock.asc()).limit(5).all()

    for product in low_stock:
        if product.stock == 0:
            msg, color = "Rupture de stock !", "red"
        else:
            msg, color = f"Seulement {product.stock} unité(s) restante(s)", "amber"

        notifications.append({
            "id": f"stock_{product.id}",
            "type": "low_stock",
            "color": color,
            "icon": "⚠️",
            "title": f"Stock faible : {product.name}",
            "message": msg,
            "time": "Maintenant",
            "link": "/products",
            "read": False
        })

    # Changements de statut récents (dernières 24 h)
    recent_status = db.session.query(Order).filter(
        Order.status.in_(["confirmed", "shipped", "delivered", "cancelled"]),
        Order.created_at >= cutoff_24h
    ).order_by(Order.created_at.desc()).limit(5).all()

    status_labels = {
        "confirmed": ("Confirmée", "green"),
        "shipped":   ("Expédiée",  "indigo"),
        "delivered": ("Livrée",    "emerald"),
        "cancelled": ("Annulée",   "red"),
    }

    for order in recent_status:
        label, color = status_labels.get(order.status, (order.status, "gray"))
        notifications.append({
            "id": f"status_{order.id}",
            "type": "status_change",
            "color": color,
            "icon": "📦",
            "title": f"Commande #{order.id} {label}",
            "message": f"Client : {order.user.name}",
            "time": "il y a moins de 24h",
            "link": "/orders",
            "read": False
        })

    # Tri : nouvelles commandes → stock → changements de statut
    type_order = {"new_order": 0, "low_stock": 1, "status_change": 2}
    notifications.sort(key=lambda n: type_order.get(n["type"], 9))

    return jsonify({"count": len(notifications), "notifications": notifications}), 200


# =====================================================================
# SUPPRESSION
# =====================================================================

@app.route("/product/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash("Produit introuvable.", "error")
        return redirect(url_for("products"))

    product_name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f"Produit '{product_name}' supprimé avec succès.", "success")
    return redirect(url_for("products"))