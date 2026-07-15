"""Sunday weekly review. Same code path as briefing, different prompt."""
from datetime import date
from .briefing import main as briefing_main
import sys

if __name__ == "__main__":
    today = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    sys.argv = ["weekly_review", "weekly", today]
    briefing_main()
