from fastapi import APIRouter
from course_esum.api.v1.endpoints import evaluations, jobs

v1_router = APIRouter(prefix="/evaluations")
v1_router.include_router(evaluations.router)
v1_router.include_router(jobs.router)
