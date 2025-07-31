import os
import motor.motor_asyncio
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

app = FastAPI()

# MongoDB
client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_DB_NAME")]
photo_collection = db.get_collection("photos")

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Welcome to Photo Gallery API"}

@app.get("/photos", response_model=dict)
async def get_all_photos(page: int = 1, limit: int = 50):
    """Lấy tất cả ảnh với phân trang, sắp xếp theo ngày tạo mới nhất"""
    try:
        # Đảm bảo page và limit hợp lệ
        if page < 1:
            page = 1
        if limit < 1:
            limit = 10

        # Tính số bản ghi cần bỏ qua
        skip = (page - 1) * limit

        # Lấy tổng số ảnh
        total_photos = await photo_collection.count_documents({})

        # Lấy danh sách ảnh với phân trang
        photos_cursor = photo_collection.find().sort("created_at", -1).skip(skip).limit(limit)
        photos = await photos_cursor.to_list(length=limit)

        # Chuyển ObjectId thành string để serialize
        for photo in photos:
            photo["_id"] = str(photo["_id"])

        # Tính tổng số trang
        total_pages = (total_photos + limit - 1) // limit

        return {
            "photos": photos,
            "page": page,
            "limit": limit,
            "total_photos": total_photos,
            "total_pages": total_pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching photos: {str(e)}")

@app.post("/photos/upload")
async def upload_photo(
    title: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload ảnh lên Cloudinary và lưu thông tin vào MongoDB"""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        # Upload lên Cloudinary
        upload_result = cloudinary.uploader.upload(
            file.file, 
            resource_type="auto"
        )
        
        # Tạo document mới trong MongoDB
        photo_data = {
            "title": title,
            "public_id": upload_result["public_id"],
            "secure_url": upload_result["secure_url"],
            "width": upload_result.get("width", 0),
            "height": upload_result.get("height", 0),
            "created_at": datetime.utcnow()
        }
        
        result = await photo_collection.insert_one(photo_data)
        created_photo = await photo_collection.find_one({"_id": result.inserted_id})
        created_photo["_id"] = str(created_photo["_id"])  # Chuyển ObjectId thành string
        return created_photo
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during upload: {str(e)}")

@app.delete("/photos/{id}")
async def delete_photo(id: str):
    """Xóa ảnh khỏi MongoDB và Cloudinary"""
    try:
        # Kiểm tra định dạng ObjectId
        if not ObjectId.is_valid(id):
            raise HTTPException(status_code=400, detail="Invalid ID format. Must be a 24-character hex string.")
        
        object_id = ObjectId(id)
        
        # Tìm ảnh trong DB để lấy public_id
        photo_to_delete = await photo_collection.find_one({"_id": object_id})
        if not photo_to_delete:
            raise HTTPException(status_code=404, detail=f"Photo with id {id} not found")

        # Xóa ảnh khỏi Cloudinary
        cloudinary.uploader.destroy(photo_to_delete["public_id"])
        
        # Xóa ảnh khỏi MongoDB
        delete_result = await photo_collection.delete_one({"_id": object_id})
        
        if delete_result.deleted_count == 1:
            return JSONResponse(status_code=200, content={"status": "success", "message": "Photo deleted successfully"})
        
        raise HTTPException(status_code=404, detail=f"Photo with id {id} was found but could not be deleted")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during deletion: {str(e)}")