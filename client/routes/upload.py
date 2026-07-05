from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Query
from schemas import UploadResponse, PresignedUrlResponse
from core.deps import get_current_user
from core.models import User
import boto3
import uuid
from core.config import settings

router = APIRouter(tags=["Uploads"])
ALLOWED_UPLOAD_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}

# Initialize S3 Client
# Note: In production, ensure this is instantiated efficiently or once.
def get_s3_client():
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        raise HTTPException(status_code=503, detail="File storage is not configured")
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.MINIO_SECURE else ''}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )


def _validate_upload_request(file_name: str, content_type: str | None, folder: str) -> tuple[str, str]:
    if content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")

    if not file_name or "." not in file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    folder_clean = folder.strip("/")
    if not folder_clean or ".." in folder_clean:
        raise HTTPException(status_code=400, detail="Invalid upload folder")

    ext = file_name.rsplit(".", 1)[-1].lower()
    return ext, folder_clean

@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Form("uploads"), # Default folder
    current_user: User = Depends(get_current_user),
):
    """
    Upload a file to MinIO (S3).
    """
    ext, folder_clean = _validate_upload_request(file.filename or "", file.content_type, folder)
    filename = f"{folder_clean}/{uuid.uuid4()}.{ext}"
    
    s3 = get_s3_client()
    
    try:
        # Use upload_fileobj for stream upload
        s3.upload_fileobj(
            file.file,
            settings.MINIO_BUCKET,
            filename,
            ExtraArgs={'ContentType': file.content_type}
        )
    except Exception as e:
        print(f"S3 Upload Error: {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
        
    # Generate Public URL (Assuming public bucket policy logic is handled on MinIO side)
    protocol = "https" if settings.MINIO_SECURE else "http"
    url = f"{protocol}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{filename}"
    
    return {
        "url": url,
        "key": filename,
        "mime_type": file.content_type
    }
@router.get("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    file_name: str,
    content_type: str,
    folder: str = Query("uploads"),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for direct client-side upload to MinIO/S3.
    Use PUT method to upload the file to the returned upload_url.
    """
    ext, folder_clean = _validate_upload_request(file_name, content_type, folder)
    key = f"{folder_clean}/{uuid.uuid4()}.{ext}"

    s3 = get_s3_client()

    try:
        # Generate Presigned PUT URL
        upload_url = s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': settings.MINIO_BUCKET,
                'Key': key,
                'ContentType': content_type
            },
            ExpiresIn=300 # 5 minutes
        )
    except Exception as e:
        print(f"Presigned URL Error: {e}")
        raise HTTPException(status_code=500, detail="Could not generate upload URL")

    # Final Public URL
    protocol = "https" if settings.MINIO_SECURE else "http"
    public_url = f"{protocol}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{key}"

    return {
        "upload_url": upload_url,
        "public_url": public_url,
        "key": key
    }
