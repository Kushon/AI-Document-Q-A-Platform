from minio import Minio

from app.core.config import settings

minio_client = Minio(
    f"{settings.minio_host}:{settings.minio_port}",
    access_key=settings.minio_root_user,
    secret_key=settings.minio_root_password,
    secure=False,
)


def download_file(file_path: str) -> bytes:
    response = minio_client.get_object(settings.minio_bucket, file_path)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
