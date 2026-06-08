import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.db import get_db
from app.core.security import get_current_user_id
from app.models.user import User
from app.schemas import DocumentCreate, DocumentOut, DocumentUpdate
from app.services.document_service import DocumentService

document_route = APIRouter()


@document_route.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    return await DocumentService.upload(db=db, file=file, uploaded_by=current_user.id)


@document_route.get("/", response_model=List[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    return await DocumentService.list_all(db=db, user_id=current_user.id)


@document_route.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    doc = await DocumentService.get_by_document_id(db=db, document_id=document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@document_route.get("/{document_id}/status", response_model=DocumentOut)
async def get_document_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    doc = await DocumentService.get_by_document_id(db=db, document_id=document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@document_route.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: str,
    payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    doc = await DocumentService.update(db=db, document_id=document_id, payload=payload)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@document_route.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    deleted = await DocumentService.delete(db=db, document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")