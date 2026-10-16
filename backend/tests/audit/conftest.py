import pytest

from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.audit.service import Actor, record


@pytest.fixture
def event(db) -> AuditEvent:
    return record(action=actions.USER_CREATED, actor=Actor.system("test"), object_type="user", object_id="1")
