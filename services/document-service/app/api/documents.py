from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kafka import publish_document_uploaded
from app.core.security import ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE, get_current_user_id
from app.core.storage import delete_file, upload_file
from app.db.database import get_db
from app.db.models import Document
from app.schemas.document import DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Разрешены только PDF и TXT файлы")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл превышает 50 МБ")

    doc = Document(user_id=user_id, filename=file.filename, file_path="")
    db.add(doc)
    await db.flush()  # получить doc.id до коммита

    file_path = f"{user_id}/{doc.id}/{file.filename}"
    upload_file(file_path, data, file.content_type)

    doc.file_path = file_path
    await db.commit()
    await db.refresh(doc)

    await publish_document_uploaded(doc.id, user_id, file_path)

    return doc


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.user_id == user_id))
    return result.scalars().all()


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    delete_file(doc.file_path)
    await db.delete(doc)
    await db.commit()
