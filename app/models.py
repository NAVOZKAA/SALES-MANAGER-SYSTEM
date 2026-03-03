from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import db


class User(db.Model):
    __tablename__ = "user"

    id: so.Mapped[int] = so.mapped_column(primary_key=True)

    name: so.Mapped[str] = so.mapped_column(sa.String(64), nullable=False)

    # WhatsApp identity
    phone: so.Mapped[str] = so.mapped_column(sa.String(20),unique=True, index=True, nullable=False)

    # required for delivery
    address: so.Mapped[str] = so.mapped_column(sa.String(200), nullable=False)

    # optional, NOT unique for your use-case
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), nullable=True)

    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # one user -> many orders
    orders: so.Mapped[list["Order"]] = so.relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "created_at": self.created_at
        }
    def __repr__(self) -> str:
        return f"<User {self.phone}>"


class Product(db.Model):
    __tablename__ = "product"

    id: so.Mapped[int] = so.mapped_column(primary_key=True)

    sku: so.Mapped[str] = so.mapped_column(sa.String(50), unique=True, index=True, nullable=False)
    name: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)

    price: so.Mapped[float] = so.mapped_column(nullable=False)   
    stock: so.Mapped[int] = so.mapped_column(default=0, nullable=False)   
    is_active: so.Mapped[bool] = so.mapped_column(default=True, nullable=False)

    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    
    order_items: so.Mapped[list["OrderItem"]] = so.relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Product {self.sku}>"


class Order(db.Model):
    __tablename__ = "order"

    id: so.Mapped[int] = so.mapped_column(primary_key=True)

     
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default="pending", index=True, nullable=False)

    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey("user.id"), index=True, nullable=False)
    user: so.Mapped["User"] = so.relationship(back_populates="orders")

    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    
    items: so.Mapped[list["OrderItem"]] = so.relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "user": User.query.get(self.user_id).to_dict(),
            "items": [i.to_dict() for i in self.items]
        }
    
    def get_total_price(self):
        """Calculate total order value in DH"""
        total = sum(item.quantity * item.unit_price for item in self.items)
        return total
    
    def __repr__(self) -> str:
        return f"<Order {self.id} status={self.status}>"


class OrderItem(db.Model):
    __tablename__ = "order_item"

    id: so.Mapped[int] = so.mapped_column(primary_key=True)

    order_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey("order.id"), index=True, nullable=False)
    order: so.Mapped["Order"] = so.relationship(back_populates="items")

    product_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey("product.id"), index=True, nullable=False)
    product: so.Mapped["Product"] = so.relationship(back_populates="order_items")

    quantity: so.Mapped[int] = so.mapped_column(default=1, nullable=False)

    unit_price: so.Mapped[float] = so.mapped_column(nullable=False)  
    def to_dict(self):
        return {
            "product_id": self.product_id,
            "quantity": self.quantity,
            "unit_price": self.unit_price
        }
    def __repr__(self) -> str:
        return f"<OrderItem order={self.order_id} product={self.product_id} qty={self.quantity}>"
