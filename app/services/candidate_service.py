
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.candidates import Candidate
from app.schemas.response import ApiResponse
from app.schemas.candidate import CandidateCreate, CandidateOut
from app.services.helper import unique_check
from app.services.s3_processor import download_and_extract_text
class CandidateService:
    async def upload(db:AsyncSession,payload:CandidateCreate):
        try:
            if not payload :
                raise HTTPException(status_code=400, detail="No file uploaded")
            if not payload.resume_file_url:
                return ApiResponse.error(message="No document find")
            document = download_and_extract_text(
                payload.resume_file_url
            )

            print("Pages:", document['page_count'])
            print("Text Length:", document['content'])

        except Exception as e :
            return HTTPException(status_code=500,detail="failed to create candidate")
        











    async def list_all(db:AsyncSession):
        try:
            statement = select(Candidate)
            result = db.execute(statement)
            candidates = result.scalars().all()
            return ApiResponse.success(data=candidates, message="Candidates retrieved successfully")
        except Exception as e :
            return HTTPException(status_code=500, detail="failed to retrieve candidates")
    async def get_by_candidate_id(db:AsyncSession, candidate_id:str):
        try:
            candidate =  select(Candidate).where(Candidate.id == candidate_id)
            result = db.execute(candidate)
            return ApiResponse.success(data = result.scalar_one_or_none(),message="data fetch successfully")
        except:
            HTTPException(status_code=404,detail="candidate not find")
    async def delete(db:AsyncSession, candidate_id:str):
        try:
            candidate = select(Candidate).where(Candidate.id == candidate_id)
            result = db.execute(candidate)
            candidate= result.scalar_one_or_none()
            if candidate is None:
                raise HTTPException(status_code=404, detail=" candidate not find")
            db.delete(candidate)
            db.commit()
            return ApiResponse.success(message="candidate remove successfully")
        except:
            return HTTPException(status_code=404, detail="failed to remove candidate")
        
    async def update(db:AsyncSession, candidate_id:str, payload:CandidateCreate):
        try:
            candidate = select(Candidate).where(Candidate.id == candidate_id)
            result = db.execute(candidate)
            candidate = result.scalar_one_or_none()
            if candidate is None:
                raise HTTPException(status_code=404, detail=" candidate not find")
            for var, value in vars(payload).items():
                if value is not None:
                    setattr(candidate, var, value)
            db.commit()
            db.refresh(candidate)
            return ApiResponse.success(data=CandidateOut.model_validate(candidate), message="candidate updated successfully")
        except:
            return HTTPException(status_code=500, detail="failed to update candidate")
