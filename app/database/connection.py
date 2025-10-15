from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine
from app.settings.settings import Settings
from app.models.models import *

class CONNECTION:

    def __init__(self):
        settings = Settings()
        DB_CONFIG = settings.DB_CONFIG
        mysql_url = f"mysql+pymysql://{DB_CONFIG.user}:{DB_CONFIG.password}@{DB_CONFIG.host}:{DB_CONFIG.port}/{DB_CONFIG.database}"

        self.engine = create_engine(mysql_url)

    def create_db_and_tables(self):
        SQLModel.metadata.create_all(self.engine)

    def get_session(self):
        with Session(self.engine) as session:
            yield session

    @property
    def SessionDep(self):
        return Annotated[Session, Depends(self.get_session)]
