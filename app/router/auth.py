from datetime import timedelta
from typing import Annotated
from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash

from app.models.models import (
    Token
)

from app.settings.settings import Settings
from app.database.connection import SessionDep
from app.auth.auth import (
    create_access_token,
    verify_password,
    # get_current_active_user,
    get_password_hash,
)

from app.database.tables import User

settings = Settings()

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = float(settings.ACCESS_TOKEN_EXPIRE_MINUTES)

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter()

@router.post("/token")
async def login_for_access_token(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = session.query(User).where(User.username == form_data.username).first() # type: ignore

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


# @router.get("/users/me/", response_model=User)
# async def read_users_me(
#     current_user: Annotated[User, Depends(get_current_active_user)],
# ):
#     return current_user


# @router.get("/users/me/items/")
# async def read_own_items(
#     current_user: Annotated[User, Depends(get_current_active_user)],
# ):
#     return [{"item_id": "Foo", "owner": current_user.name}]

@router.post("/register/", response_model=User)
def create_user(user_data: User, session: SessionDep): # type: ignore
    existing_user_by_email = session.query(User).filter(User.email == user_data.email).first() # type: ignore
    if existing_user_by_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    base_username =  '@'+user_data.email.split('@')[0].lower().replace(" ", "_")
    username = base_username
    counter = 1
    while session.query(User).filter(User.username == username).first() is not None: # type: ignore
        username = f"{base_username}{counter}"
        counter += 1

    hashed_password = get_password_hash(user_data.hashed_password)
    user = User(
        name=user_data.name,
        username=username,
        email=user_data.email,
        hashed_password=hashed_password,
        disabled=False
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user