
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.models.candidates import Candidate
from app.schemas.response import ApiResponse
from app.schemas.candidate import CandidateCreate, CandidateOut
from app.services.s3_processor import download_and_extract_text
class CandidateService:
    @staticmethod
    async def upload(db: AsyncSession, payload: CandidateCreate):
        try:
            if not payload:
                raise HTTPException(status_code=400, detail="No payload")

            if not payload.resume_file_url:
                return ApiResponse.error(message="resume_file_url is required")
            document = await download_and_extract_text(payload.resume_file_url)

            return ApiResponse.success(data={
                "file_name" : document["file_name"],
                "page_count": document["page_count"],
                "file_size" : document["file_size"],
                "content"   : document["content"][:500],
            })

        except HTTPException:
            raise
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
        











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
            raise HTTPException(status_code=404,detail="candidate not find")
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
            raise HTTPException(status_code=404, detail="failed to remove candidate")
        
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
            raise HTTPException(status_code=500, detail="failed to update candidate")
