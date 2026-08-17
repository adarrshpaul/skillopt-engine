
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kanban.models import Base, Board
from kanban.api.boards import router, get_db
from main import app

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

# Override the get_db dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create test client
client = TestClient(app)

# Test data
test_board = {
    "name": "Test Board",
    "description": "A board for testing"
}

def test_create_board():
    response = client.post("/boards/", json=test_board)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_board["name"]
    assert data["description"] == test_board["description"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

def test_read_boards():
    # First create a board to read
    client.post("/boards/", json=test_board)

    response = client.get("/boards/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == test_board["name"]

def test_read_board():
    # First create a board
    create_response = client.post("/boards/", json=test_board)
    board_id = create_response.json()["id"]

    response = client.get(f"/boards/{board_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == board_id
    assert data["name"] == test_board["name"]

def test_read_board_not_found():
    response = client.get("/boards/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Board not found"

def test_update_board():
    # First create a board
    create_response = client.post("/boards/", json=test_board)
    board_id = create_response.json()["id"]

    update_data = {
        "name": "Updated Board",
        "description": "Updated description"
    }

    response = client.put(f"/boards/{board_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]
    assert data["id"] == board_id

def test_delete_board():
    # First create a board
    create_response = client.post("/boards/", json=test_board)
    board_id = create_response.json()["id"]

    response = client.delete(f"/boards/{board_id}")
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(f"/boards/{board_id}")
    assert get_response.status_code == 404
