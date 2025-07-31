# main.py
import os
import motor.motor_asyncio
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from bson import ObjectId
from typing import List, Optional
from datetime import datetime
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
# Tải biến môi trường
load_dotenv()

# --- Cấu hình ---
# FastAPI App
app = FastAPI()

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)
print(os.getenv("MONGO_URI"))
# MongoDB
client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME")]
photo_collection = db.get_collection("photos")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong sản phẩm thực tế, hãy giới hạn lại
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models (Pydantic) ---
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        return {
            "type": "string",
            "examples": ["507f1f77bcf86cd799439011"]
        }


class PhotoModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: str
    public_id: str
    secure_url: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Welcome to Photo Gallery API"}

@app.get("/photos", response_model=List[PhotoModel])
async def get_all_photos():
    """Lấy tất cả ảnh, sắp xếp theo ngày tạo mới nhất"""
    photos = await photo_collection.find().sort("created_at", -1).to_list(100)
    return photos

@app.post("/photos/upload", response_model=PhotoModel)
async def upload_photo(
    title: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload ảnh lên Cloudinary và lưu thông tin vào MongoDB"""
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        # Upload lên Cloudinary
        upload_result = cloudinary.uploader.upload(file.file, resource_type="auto")
        
        # Tạo document mới để lưu vào DB
        photo_data = {
            "title": title,
            "public_id": upload_result["public_id"],
            "secure_url": upload_result["secure_url"],
            "created_at": datetime.utcnow()
        }
        
        new_photo = await photo_collection.insert_one(photo_data)
        created_photo = await photo_collection.find_one({"_id": new_photo.inserted_id})
        return created_photo
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.delete("/photos/{id}")
async def delete_photo(id: str):
    """Xóa ảnh khỏi MongoDB và Cloudinary"""
    try:
        object_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Tìm ảnh trong DB để lấy public_id
    photo_to_delete = await photo_collection.find_one({"_id": object_id})
    if not photo_to_delete:
        raise HTTPException(status_code=404, detail=f"Photo with id {id} not found")

    try:
        # Xóa ảnh khỏi Cloudinary
        cloudinary.uploader.destroy(photo_to_delete["public_id"])
        
        # Xóa ảnh khỏi MongoDB
        delete_result = await photo_collection.delete_one({"_id": object_id})
        
        if delete_result.deleted_count == 1:
            return {"status": "success", "message": "Photo deleted"}
        
        raise HTTPException(status_code=404, detail=f"Photo with id {id} not found")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during deletion: {str(e)}")
