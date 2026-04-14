from minio import Minio
from minio.error import S3Error

from app.core.config import settings

minio_client = Minio(
    f"{settings.minio_host}:{settings.minio_port}",
    access_key=settings.minio_root_user,
    secret_key=settings.minio_root_password,
    secure=False,
)


def ensure_bucket() -> None:
    if not minio_client.bucket_exists(settings.minio_bucket):
        minio_client.make_bucket(settings.minio_bucket)


def upload_file(file_path: str, data: bytes, content_type: str) -> None:
    import io
    minio_client.put_object(
        settings.minio_bucket,
        file_path,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def delete_file(file_path: str) -> None:
    try:
        minio_client.remove_object(settings.minio_bucket, file_path)
    except S3Error:
        pass
