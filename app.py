from app import app, db
from app.models import User, Product, Order, OrderItem
from datetime import datetime, timezone
import sqlalchemy as sa
import sqlalchemy.orm as so




@app.shell_context_processor
def make_shell_context():
    return {'sa': sa, 'so': so, 'db': db, 'User': User, 'Product': Product, 'Order': Order, 'OrderItem': OrderItem}

if __name__ == '__main__':
    app.run(debug=True)