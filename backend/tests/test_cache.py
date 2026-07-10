from unittest.mock import Mock

from app.core.config import Settings
from app.infra.redis import ProjectCache


def test_cache_prefix_and_project_clear() -> None:
    client = Mock()
    client.scan_iter.return_value = iter(["dawenzhang:one", "dawenzhang:two"])
    client.delete.return_value = 2
    cache = ProjectCache(client=client, settings=Settings(_env_file=None))

    cache.set("one", "value")
    assert client.set.call_args.args[0] == "dawenzhang:one"
    cache.clear_project()
    client.delete.assert_called_once_with("dawenzhang:one", "dawenzhang:two")
    assert not any(call.args and call.args[0] in {"FLUSHALL", "FLUSHDB"} for call in client.method_calls)
