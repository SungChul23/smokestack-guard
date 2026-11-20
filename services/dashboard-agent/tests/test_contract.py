import pytest
from pydantic import ValidationError

from app.agent.contract import ChatRequest


def test_message_only_is_ok():
    assert ChatRequest(message="  어제 평균  ").message == "어제 평균"


def test_resume_only_is_ok():
    request = ChatRequest(resume={"card_id": "c1", "option_id": "yesterday"})
    assert request.message is None and request.resume.option_id == "yesterday"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": "a", "resume": {"card_id": "c", "option_id": "o"}},
        {"message": "   "},
        {"message": "x" * 4001},
        {"message": "a", "userId": "someone"},
        {"message": "a", "context": {"allowedStackIds": ["1:1"]}},
    ],
)
def test_invalid_bodies_are_rejected(body):
    with pytest.raises(ValidationError):
        ChatRequest(**body)
