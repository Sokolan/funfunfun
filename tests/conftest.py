import pytest

from timetracker.db import init_db

from tests._util import make_config


@pytest.fixture
def config(tmp_path):
    cfg = make_config(tmp_path)
    init_db(cfg.db_path)
    return cfg
