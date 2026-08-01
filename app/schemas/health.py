from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
