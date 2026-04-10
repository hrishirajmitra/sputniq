import pytest
from datetime import timedelta
from fastapi import HTTPException
from jose import jwt

from sputniq.api.auth import create_access_token, verify_token, SECRET_KEY, ALGORITHM

@pytest.mark.asyncio
async def test_create_and_verify_token():
    token = create_access_token({"sub": "admin", "role": "operator"})
    data = await verify_token(token)
    
    assert data.username == "admin"
    assert data.role == "operator"

@pytest.mark.asyncio
async def test_verify_token_invalid():
    bad_token = "eyJiYWQiOiAidG9rZW4iH0"
    
    with pytest.raises(HTTPException) as exc:
        await verify_token(bad_token)
        
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"

@pytest.mark.asyncio
async def test_verify_token_expired():
    token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-1))
    
    with pytest.raises(HTTPException) as exc:
        await verify_token(token)
        
    assert exc.value.status_code == 401
    assert "validate credentials" in str(exc.value.detail)

