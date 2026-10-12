from pydantic import BaseModel, Field
from .models import Role


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    full_name: str = ""
    role: Role


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    phone: str = ""
    role: Role
    is_active: bool = True
    model_config = {"from_attributes": True}


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    store_name: str = Field(min_length=2, max_length=100)
    address: str = Field(default="", max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=6, max_length=100)


class StoreCreate(BaseModel):
    name: str
    address: str = ""
    phone: str = ""
    user_id: int | None = None


class StoreOut(StoreCreate):
    id: int
    approved: bool = True
    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str
    unit: str = "dona"
    price: float = Field(default=0, ge=0)
    category: str = ""
    description: str = ""
    is_active: bool = True


class ProductOut(ProductCreate):
    id: int
    model_config = {"from_attributes": True}
