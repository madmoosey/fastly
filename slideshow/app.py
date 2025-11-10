import os
import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from mangum import Mangum

# Load environment variables locally
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET")
URL_EXPIRES_SECONDS = int(os.getenv("URL_EXPIRES_SECONDS", 300))

# Initialize S3 client
s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

app = FastAPI(title="Slideshow API (Python + FastAPI)")

# Enable CORS for browsers (tighten origin in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".mov", ".avi")

@app.get("api/")
def root():
    return {"message": "Serverless Slideshow API (Python) ✅"}

@app.get("/api/images")
def get_images():
    try:
        # List objects from S3
        response = s3.list_objects_v2(Bucket=S3_BUCKET)
        contents = response.get("Contents", [])

        media = [f for f in contents if f["Key"].lower().endswith(MEDIA_EXTENSIONS)]

        # Generate presigned URLs
        items = []
        for f in media:
            url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": S3_BUCKET, "Key": f["Key"]},
                ExpiresIn=URL_EXPIRES_SECONDS,
            )
            items.append({
                "key": f["Key"],
                "url": url,
                "size": f["Size"],
                "lastModified": f["LastModified"].isoformat(),
                "isVideo": f["Key"].lower().endswith((".mp4", ".webm", ".mov", ".avi")),
            })

        return {"images": sorted(items, key=lambda x: x["lastModified"], reverse=True)}

    except Exception as e:
        print("Error generating URLs:", e)
        return {"error": "Failed to list or sign S3 files"}

# Lambda entrypoint
handler = Mangum(app)