import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.api.deps import get_db
from app.models.projects import Project
import uuid
from unittest.mock import AsyncMock

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    # Create the tables.
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop the tables.
        Base.metadata.drop_all(bind=engine)


def test_send_message_and_verify_cli_source(db_session, tmpdir, monkeypatch):
    # 1. Create a project to associate the message with
    project_id = str(uuid.uuid4())
    repo_path = tmpdir.mkdir("repo")
    project = Project(id=project_id, name="Test Project", repo_path=str(repo_path))
    db_session.add(project)
    db_session.commit()

    # Mock the background task execution function
    mock_execute_act_task = AsyncMock()
    monkeypatch.setattr("app.api.chat.act.execute_act_task", mock_execute_act_task)

    # 2. Send a message using the 'act' endpoint
    conversation_id = str(uuid.uuid4())
    test_instruction = "Test instruction"
    test_cli_preference = "claude"

    act_response = client.post(
        f"/api/chat/{project_id}/act",
        json={
            "instruction": test_instruction,
            "conversation_id": conversation_id,
            "cli_preference": test_cli_preference,
        },
    )
    assert act_response.status_code == 200
    act_data = act_response.json()
    assert act_data["conversation_id"] == conversation_id

    # Assert that the background task was called
    mock_execute_act_task.assert_called_once()

    # 3. Retrieve the messages for the conversation
    messages_response = client.get(
        f"/api/chat/{project_id}/messages?conversation_id={conversation_id}"
    )
    assert messages_response.status_code == 200
    messages_data = messages_response.json()

    # 4. Verify that the user's message has the correct cli_source
    assert len(messages_data) > 0
    user_message = messages_data[0]
    assert user_message["role"] == "user"
    assert "Test instruction" in user_message["content"]
    assert user_message["cli_source"] == test_cli_preference
