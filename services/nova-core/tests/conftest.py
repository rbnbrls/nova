import sys
from os.path import abspath, dirname, join

# Ensure app directory is in Python path for test execution
sys.path.insert(0, abspath(join(dirname(__file__), "..")))
