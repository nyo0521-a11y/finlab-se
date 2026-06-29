import sys
from pathlib import Path

# .github/scripts をインポートパスに通す（テストから各スクリプトを import するため）
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
