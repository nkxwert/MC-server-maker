"""Keep tests away from the real Documents folder: use a temp data folder for every test module."""

import os
import tempfile

os.environ.setdefault("MCSM_HOME", tempfile.mkdtemp(prefix="mcsm-test-"))
