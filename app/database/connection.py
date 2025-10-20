from typing import Annotated
from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from app.settings.settings import Settings
from app.database.tables import *

# class CONNECTION:

#     def __init__(self):
#         settings = Settings()
#         DB_CONFIG = settings.DB_CONFIG
#         db_url = f"postgresql+psycopg2://{DB_CONFIG.user}:{DB_CONFIG.password}@{DB_CONFIG.host}:{DB_CONFIG.port}/{DB_CONFIG.database}"

#         self.engine = create_engine(db_url)

#     def create_db_and_tables(self):
#         SQLModel.metadata.create_all(self.engine)

#     def get_session(self):
#         with Session(self.engine) as session:
#             yield session

#     @property
#     def SessionDep(self):
#         return Annotated[Session, Depends(self.get_session)]

settings = Settings()
DB_CONFIG = settings.DB_CONFIG
db_url = f"postgresql+psycopg2://{DB_CONFIG.user}:{DB_CONFIG.password}@{DB_CONFIG.host}:{DB_CONFIG.port}/{DB_CONFIG.database}"

engine = create_engine(db_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
