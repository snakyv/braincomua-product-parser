"""Initialize Django so standalone scripts in ``modules`` can use the ORM."""

import os
import sys
from pathlib import Path

import django


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "braincomua_project.settings")
django.setup()
